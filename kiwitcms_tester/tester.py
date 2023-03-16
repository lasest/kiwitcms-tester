import dataclasses
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


@dataclass()
class KiwiBackendConfig:
    """Stores data which will be written to ~/.tcms.conf to be used by Kiwi Backend to connect to the api"""
    kiwi_url: str
    username: str
    password: str


@dataclass
class Environment:
    """Stores environment variables which will be set before using tcms-junit.xml-plugin"""
    tcms_product: str
    tcms_product_version: str
    tcms_build: str
    tcms_plan_id: str = ""


@dataclass
class TestDescription:
    """Holds some data necessary to upload test results to Kiwi
    :param test_plan_id: Stores id of Test plan as in kiwi database
    :param test_result_path: Absolute path to the junit.xml file containing result of test execution
    """
    test_plan_id: str
    test_result_path: str


class Tester:

    def __init__(self, tests_dir_path: str, output_dir_path: str, environment: Environment):
        """
        Creates Tester instance and reads some assets
        :param tests_dir_path: path to the directory containing pytest test files. Each file should start with test_
        :param output_dir_path: path to the directory where output junit.xml files will be written
        """
        self.tests_path: str = tests_dir_path
        self.output_dir_path: str = output_dir_path
        self.environment = environment
        self.performed_tests: list[TestDescription] = []

        # Get paths to assets
        upload_script_template_path = str(
            importlib.resources.path("kiwitcms_tester.assets", "upload_test_results_template.sh"))
        self.conftest_script_path = str(importlib.resources.path("kiwitcms_tester.assets", "conftest.py"))
        kiwi_backend_api_config_path = str(importlib.resources.path("kiwitcms_tester.assets", "template_tcms.conf"))

        # Read template assets
        with open(upload_script_template_path, 'r') as f:
            self.upload_script_template = string.Template(f.read())

        with open(kiwi_backend_api_config_path, 'r') as f:
            self.kiwi_backend_config_template = string.Template(f.read())

    def config_kiwi_credentials(self, config: KiwiBackendConfig) -> None:
        """
        Creates a .tcms.conf file which will be used by kiwi backend to connect to the api. The information will be
        stored at ~/.tcms.conf in UNENCRYPTED form
        :param config: dataclass holding a URL of your kiwi instance (i.e. kiwi.example.com) and user credentials
        """
        config.kiwi_url = config.kiwi_url.rstrip("/")
        if not config.kiwi_url.endswith("/xml-rpc"):
            config.kiwi_url = config.kiwi_url + "/xml-rpc/"
        else:
            config.kiwi_url = config.kiwi_url + "/"
        mapping = dataclasses.asdict(config)

        config_text = self.kiwi_backend_config_template.substitute(mapping)
        home_path = os.path.expanduser("~")
        with open(os.path.join(home_path, ".tcms.conf"), "w") as fh:
            fh.write(config_text)

    @staticmethod
    def load_module(module_name: str, module_path: str):
        """
        Helper method to load a test module by its path
        :param module_name: name of the module, i.e. filename of the module w/o .py
        :param module_path: path to the module
        :return: module object
        """
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)

        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def perform_all_tests(self) -> None:
        """Runs all tests in test_ files found in the self.tests_path directory"""
        test_files = [filename for filename in os.listdir(self.tests_path) if filename.startswith("test")]

        for filename in test_files:
            self.perform_single_test(filename)

    def perform_single_test(self, filename: str, method_selector: str = "") -> None:
        """
        Runs a single test file with specified filename, which will be searched for in the self.tests_path directory
        :param filename: filename of the test file
        :param method_selector: string which will be passed as pytest -k argument to filter test cases by their function/method names
        :rtype: object
        """
        module_name = filename.replace(".py", "")
        module_path = os.path.join(self.tests_path, filename)

        test_module = Tester.load_module(module_name, module_path)
        try:
            plan_id = test_module.TEST_PLAN_ID
        except AttributeError:
            print(f"Failed to get the value of {test_module}.TEST_PLAN_ID. Does the module implement it?")
            plan_id = ""

        test_filepath = os.path.join(self.tests_path, f"{module_name}.py")
        output_path = os.path.join(self.output_dir_path, f"{plan_id}-{module_name}.xml")

        if not os.path.exists(os.path.join(self.tests_path, "conftest.py")):
            shutil.copy(self.conftest_script_path, self.tests_path)

        pytest_args = ["--junit-xml", output_path]
        if method_selector:
            pytest_args.append("-k")
            pytest_args.append(method_selector)

        pytest_args.append(test_filepath)
        pytest.main(pytest_args)

        test = TestDescription(test_plan_id=plan_id, test_result_path=output_path)
        self.performed_tests.append(test)

    def get_performed_tests_from_test_results(self):
        result_filenames = [filename for filename in os.listdir(self.output_dir_path) if filename.endswith(".xml")]
        for filename in result_filenames:
            path = os.path.join(self.output_dir_path, filename)
            plan_id = filename.split("-")[0]
            self.performed_tests.append(TestDescription(test_plan_id=plan_id,
                                                        test_result_path=path))

    def upload_all_test_results(self) -> None:
        """
        Uploads all test results to Kiwi. Test results are expected to be junit.xml files located
        at self.output_dir_path
        """
        if not self.performed_tests:
            print("This tester performed no tests. Getting list of test results from output dir...")
            self.get_performed_tests_from_test_results()

        print("\nStarting batch upload of test results\n")
        for test in self.performed_tests:
            self.upload_single_test_result(test)
        print("Finished batch upload of test results")

    def upload_single_test_result(self, test_description: TestDescription) -> None:
        """
        Uploads result of a single Test plan which is expected to be in a separate junit.xml file
        :param test_description:
        """
        self.environment.tcms_plan_id = test_description.test_plan_id
        mapping = dataclasses.asdict(self.environment)
        mapping["test_result_path"] = test_description.test_result_path

        print(f'Uploading test results for Test plan ID: {test_description.test_plan_id}')

        script = self.upload_script_template.substitute(mapping)
        popen = subprocess.Popen(script, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        std_out, std_err = popen.communicate()

        if std_out:
            print(f"Output: {std_out.decode()}")
        if std_err:
            print(f"ERROR: {std_err.decode()}\n")
        else:
            print("Success\n")
