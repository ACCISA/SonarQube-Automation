import argparse
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import time
import requests
import re
import subprocess
import os
import logging
import getpass
from tqdm import tqdm

AVAILABLE_PROJECTS = ["Csv","Jsoup","Mockito","Time","Math"]
DEFECTS4J_CHECKOUT = "checkout -p {} -v {} -w {}"
DEFECTS4J_COMPILE = "compile"
DEFECTS4J_TEST = "test"
DEFECTS4J_COVERAGE = "coverage"
DEFECTS4J_PATH_TEST = "info -p Lang"
user_token = None
project_token = None
logging.basicConfig(
    level=logging.DEBUG,  # Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
)

def arguments():
    parser = argparse.ArgumentParser(description="arguments to automate data collection")

    parser.add_argument("-w", required=True,type=str, help="directory to create defects4j checkouts")
    parser.add_argument("-d", required=True,type=str, help="full defects4j binary path")
    parser.add_argument("-s", required=True,type=str, help="full sonar-scanner binary path")
    parser.add_argument("-p", required=True,type=str, help="defects4j project to automate")
    parser.add_argument("-t", required=True,type=str, help="sonarqube user token")
    parser.add_argument("-k", required=True,type=str, help="sonarqube project token")

    args = parser.parse_args()

    return args

def execute_command(path,command,cwd=None):
    if cwd is None:
        result = subprocess.run([path+"/defects4j"]+command, capture_output=True,text=True)
    else:
        result = subprocess.run([path+"/defects4j"]+command, capture_output=True,text=True, cwd=cwd)

    stdout = result.stdout
    stderr = result.stderr

    return (True,stderr+stdout)

def execute_scanner(path,command,cwd=None):
    if cwd is None:
        result = subprocess.run([path+"/sonar-scanner"]+command, capture_output=True,text=True)
    else:
        result = subprocess.run([path+"/sonar-scanner"]+command, capture_output=True,text=True, cwd=cwd)

    stdout = result.stdout
    stderr = result.stderr

    return (True,stderr+stdout)


def test_defects4j_path(path):
    status, output = execute_command(path, DEFECTS4J_PATH_TEST.split())
    if status is False:
        logging.error(output)

    return status


def is_choosen_project(project):
    if project in AVAILABLE_PROJECTS: return True
    return False

def get_project_bugs(path, project):
    to_replace = f"/projects/{project}/trigger_tests"
    trigger_tests_path = path.replace("bin",to_replace)

    trigger_tests = sorted(os.listdir(trigger_tests_path))

    return trigger_tests


def checkout_all_versions(path, project, trigger_tests, w):

    for test in tqdm(trigger_tests, desc=f"Checking out all versions of {project}",ncols=100):
        checkout = DEFECTS4J_CHECKOUT.format(project, test+"b", w+"/345/"+test)
        status, output = execute_command(path, checkout.split())

def get_tests(w):
    tests_path = w+"/345/"
    return sorted(os.listdir(tests_path))

def fetch_cyclomatic_complexity():
    global user_token
    url = "http://localhost:9000/api/measures/component?additionalFields=period%2Cmetrics&component=a&metricKeys=complexity"

    headers = {
        'Content-Type': 'application/json',
            'Authorization': f"Bearer {user_token}"
    }
    logging.info("user_token="+user_token)

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()  # Return the JSON response
    else:
        logging.error(f"Request failed with status code {response.status_code}")
        exit()


def get_cyclomatic_complexity(path, project, trigger_tests, w, token):
    complexities = {}

    for test in tqdm(trigger_tests, desc=f"Calculating cyclomatic complexities for {project}", ncols=100):
        cwd = w+"/345/"+test
        status, output = execute_scanner(path,f"-Dsonar.projectKey=a -Dsonar.sources=. -Dsonar.host.url=http://localhost:9000 -Dsonar.token={token} -Dsonar.java.binaries=target/classes".split(), cwd=cwd)

        logging.error(test)
        logging.error(output)
        time.sleep(5)
        data = fetch_cyclomatic_complexity()
        complexities[test] = data['component']['measures'][0]['value']


    logging.info("Completed scanning versions")
    logging.info(complexities)
    return complexities
  
def get_coverage(path, project, trigger_tests,w):
    coverages = {}
    for test in tqdm(trigger_tests, desc=f"Calculating coverages for {project}", ncols=100):
        cwd = w+"/345/"+test
        status, output = execute_command(path, DEFECTS4J_COVERAGE.split(), cwd=cwd)

        pattern = r"Lines total:\s*(\d+)\s*Lines covered:\s*(\d+)\s*Conditions total:\s*(\d+)\s*Conditions covered:\s*(\d+)\s*Line coverage:\s*([\d.]+)%\s*Condition coverage:\s*([\d.]+)%"
        
        match = re.search(pattern, output)

        if match is None:
            logging.error("Failed to capture coverage")
            exit()
        lines_total = int(match.group(1))
        lines_covered = int(match.group(2))
        conditions_total = int(match.group(3))
        conditions_covered = int(match.group(4))
        line_coverage = float(match.group(5))
        condition_coverage = float(match.group(6))
        coverages[test] = {
            "line_coverage":line_coverage,
            "condition_coverage":condition_coverage
        }
    logging.info(coverages)
    return coverages

def compile_all_versions(path, project, trigger_tests, w):

    for test in tqdm(trigger_tests, desc=f"Compiling versions for {project}", ncols=100):
        cwd = w+"/345/"+test
        status, output = execute_command(path, DEFECTS4J_COMPILE.split(), cwd=cwd)
    logging.info("Completed compilation of all versions")

def get_testing_time(path, project, trigger_tests, w):
    logging.info(f"Getting testing times for project {project}")
    delays = {}
    for test in tqdm(trigger_tests, desc=f"Getting testing delays for {project}", ncols=100):
        cwd = w+"/345/"+test
        start_time = datetime.now()
        status, output = execute_command(path, DEFECTS4J_TEST.split(), cwd=cwd)
        end_time = datetime.now()
        delay = end_time - start_time
        delays[test] = delay

    logging.info("Completed delay calculation")
    logging.info(delays)
    return delays

def save_complexities_graph(project, complexities):

    versions = sorted(complexities.keys(), key=lambda x: int(x))
    x = [int(v) for v in versions]
    y = [int(complexities[v]) for v in versions]

    plt.figure(figsize=(10, 6))
    plt.plot(x, y, marker='o', linestyle='-', color='blue')
    plt.title(f'Cyclomatic Complexity Over {project} Project Versions')
    plt.xlabel('Version')
    plt.ylabel('Cyclomatic Complexity')
    plt.grid(True)
    plt.xticks(x)
    plt.tight_layout()

    plt.savefig(f"{project}_cyclomatic_complexity.png")
    logging.info(f"Graph saved as '{project}_cyclomatic_complexity.png'")

def save_test_delays_graph(project, delays):
    delays_in_seconds = {k: v.total_seconds() if isinstance(v, timedelta) else v for k, v in delays.items()}

    sorted_versions = sorted(delays_in_seconds.items(), key=lambda x: int(x[0]))
    versions = [v[0] for v in sorted_versions]
    delay_values = [v[1] for v in sorted_versions]

    plt.figure(figsize=(10, 6))
    plt.plot(versions, delay_values, marker='o', linestyle='-', color='purple')
    plt.title('Delays Between Project Versions')
    plt.xlabel('Version')
    plt.ylabel('Delay (seconds)')
    plt.grid(True)
    plt.tight_layout()

    plt.savefig(f"{project}_test_delays.png")
    logging.info(f"Graph saved as '{project}_test_delays.png'")

def save_coverage_graph(project, coverages):
    sorted_items = sorted(coverages.items(), key=lambda x: x[0])
    tests = [key for key, _ in sorted_items]
    line_coverage = [val["line_coverage"] for _, val in sorted_items]
    cond_coverage = [val["condition_coverage"] for _, val in sorted_items]

    plt.figure(figsize=(10, 6))
    plt.plot(tests, line_coverage, marker='o', label='Line Coverage', color='blue')
    plt.plot(tests, cond_coverage, marker='s', label='Condition Coverage', color='orange')

    plt.title('Test Coverage Over Time')
    plt.xlabel('Test')
    plt.ylabel('Coverage (%)')
    plt.ylim(0, 100)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    plt.savefig(f"{project}_coverage.png")
    logging.info(f"Coverage graph saved as '{project}_coverage.png'")

def main():
    global user_token
    global project_token
    args = arguments()
    project = args.p
    path = args.d
    w = args.w
    user_token = args.t
    project_token = args.k
    scanner = args.s

    if project not in AVAILABLE_PROJECTS:
        logging.error(f"{project} is not a project we decided to work on")
        logging.error(AVAILABLE_PROJECTS)
        return

    trigger_tests = get_project_bugs(path, project)

    if not test_defects4j_path(path):
        logging.error("invalid defects4j bin path")
        return
    
    checkout_all_versions(path, project, trigger_tests, w)
    logging.info("Done checking out all versions")
    trigger_tests = get_tests(w)
    logging.info("Updated test files")
    logging.info(trigger_tests)

    coverages = get_coverage(path, project, trigger_tests, w)

    compile_all_versions(path, project, trigger_tests, w)
    
    complexities = get_cyclomatic_complexity(scanner, project, trigger_tests,  w, project_token)

    delays = get_testing_time(path, project, trigger_tests, w)

    save_coverage_graph(project, coverages)
    save_complexities_graph(project, complexities)
    save_test_delays_graph(project, delays)



main()
