import argparse
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

logging.basicConfig(
    level=logging.DEBUG,  # Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
)

def arguments():
    parser = argparse.ArgumentParser(description="arguments to automate data collection")

    parser.add_argument("-w", required=True,type=str, help="directory to create defects4j checkouts")
    parser.add_argument("-d", required=True,type=str, help="full defects4j binary path")
    parser.add_argument("-p", required=True,type=str, help="defects4j project to automate")
    parser.add_argument("-t", required=True,type=str, help="sonarqube user token")

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

def compile_all_versions(path, project, trigger_tests, w):

    for test in tqdm(trigger_tests, desc=f"Compiling versions for {project}", ncols=100):
        cwd = w+"/345/"+test
        status, output = execute_command(path, DEFECTS4J_COMPILE.split(), cwd=cwd)
        logging.info(output)

def fetch_cyclomatic_complexity(cookie):
    url = "http://localhost:9000/api/measures/component?additionalFields=period%2Cmetrics&component=a&metricKeys=complexity"

    headers = {
        'Content-Type': 'application/json'
    }

    cookies = {
        'JWT-SESSION': cookie
    }

    response = requests.get(url, headers=headers, cookies=cookies)

    if response.status_code == 200:
        return response.json()  # Return the JSON response
    else:
        logging.error(f"Request failed with status code {response.status_code}")
        exit()

def get_jwt_token(username, password):
    url = "http://localhost:9000/api/authentication/login"

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'http://localhost:9000/sessions/new?return_to=%2F',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'http://localhost:9000',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin'
    }

    form_data = {
            "username":username,
            "password":password
    }

    response = requests.post(url, headers=headers, data=form_data)
    set_cookie_header = response.headers.get('Set-Cookie')
    print(set_cookie_header)


def main():

    args = arguments()
    project = args.p
    path = args.d
    w = args.w

    print("Provide your sonarqube-server credentials to generate JWT Token")
    print("Please make sure you've logged in once at localhost:9000")
    username = input("Username:")
    password = getpass.getpass("Password:")

    get_jwt_token(username, password)

    if project not in AVAILABLE_PROJECTS:
        logging.error(f"{project} is not a project we decided to work on")
        logging.error(AVAILABLE_PROJECTS)
        return

    trigger_tests = get_project_bugs(path, project)

    if not test_defects4j_path(path):
        logging.error("invalid defects4j bin path")
        return
    
    checkout_all_versions(path, project, trigger_tests, w)

    get_coverage(path, project, trigger_tests, w)

    compile_all_versions(path, project, trigger_tests, w)


main()
