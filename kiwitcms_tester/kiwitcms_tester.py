import os
import importlib
import importlib.resources
import importlib.util
from dataclasses import dataclass
import subprocess
import string
import sys
import shutil

import pytest


@dataclass
class TestDescription:
    """Holds some data necessary to upload test results to Kiwi
    :param test_plan_id: Stores id of Test plan as in kiwi database
    :param test_result_path: Absolute path to the junit.xml file containing result of test execution
    """
    test_plan_id: str
    test_result_path: str


class Tester:

    def __init__(self, tests_dir_path: str, output_dir_path: str):
        """
        :param tests_dir_path: path to the directory containing pytest test files. Each file should start with test_
        :param output_dir_path: path to the directory where output junit.xml files will be written
        """
        self.tests_path = tests_dir_path
        self.output_dir_path = output_dir_path
        self.performed_tests: list[TestDescription] = []

        self.environment_variables = {
            "product": "M-EDC\ 2.0",
            "version": "unspecified",
            "build": "1",
            "plan_id": None,
            "test_result_path": None
        }

        upload_script_template_path = str(importlib.resources.path("assets", "upload_test_results_template.sh"))
        self.conftest_script_path = str(importlib.resources.path("assets", "conftest.py"))
        kiwi_backend_api_config_path = str(importlib.resources.path("assets", "template_tcms.conf"))

        with open(str(upload_script_template_path), 'r') as f:
            self.upload_script_template = string.Template(f.read())

        with open(kiwi_backend_api_config_path, 'r') as f:
            self.kiwi_backend_config_template = string.Template(f.read())

    def config_kiwi_credentials(self, kiwi_url, username, password):
        credentials = {
            "kiwi_url": kiwi_url + "/xml-rpc",
            "username": username,
            "password": password
        }

        config = self.kiwi_backend_config_template.substitute(credentials)
        home_path = os.path.expanduser("~")
        with open(os.path.join(home_path, ".tcms.conf"), "w") as fh:
            fh.write(config)

    @staticmethod
    def load_module(module_name: str, module_path: str):
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)

        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def perform_all_tests(self):
        test_files = [filename for filename in os.listdir(self.tests_path) if filename.startswith("test")]

        for filename in test_files:
            self.perform_single_test(filename)

    def perform_single_test(self, filename):
        module_name = filename.replace(".py", "")
        module_path = os.path.join(self.tests_path, filename)
        test_module = Tester.load_module(module_name, module_path)

        test_filepath = os.path.join(self.tests_path, f"{module_name}.py")
        output_path = os.path.join(self.output_dir_path, f"{module_name}.xml")

        if not os.path.exists(os.path.join(self.tests_path, "conftest.py")):
            shutil.copy(self.conftest_script_path, self.tests_path)

        pytest.main(["--junit-xml", output_path, self.conftest_script_path, test_filepath])
        test = TestDescription(test_plan_id=test_module.TEST_PLAN_ID, test_result_path=output_path)
        self.performed_tests.append(test)

    def upload_all_test_results(self):
        for test in self.performed_tests:
            self.upload_single_test_result(test)

    def upload_single_test_result(self, test_description: TestDescription):
        environment = self.environment_variables.copy()
        environment["plan_id"] = test_description.test_plan_id
        environment["test_result_path"] = test_description.test_result_path

        script = self.upload_script_template.substitute(environment)
        subprocess.Popen(script, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
