# Kiwitcms-tester: a package to simplify uploading test results to KiwiTCMS

This package provides a class to simplify running tests and uploading their results to KiwiTCMS. The general workflow is to:

1. Execute all PyTest test files in a given directory

2. Export the results of every test file in a separate junit.xml file

3. Upload the results from each junit.xml file to a separate Test plan within KiwiTCMS

It can be performed with the following snippet:

```
from kiwitcms_tester.tester import Tester, Environment, KiwiBackendConfig


tests_path = "path to tests folder"
output_path = "path to output folder"

kiwi_env = Environment(tcms_product="your product name as specified in KiwiTCMS",
                       tcms_product_version="your product version as specified in KiwiTCMS",
                       tcms_build="1")

kiwi_config = KiwiBackendConfig(kiwi_url="https://tcms.example.com",
                                username="user",
                                password='password123')

tester = Tester(tests_path, output_path, kiwi_env)
tester.config_kiwi_credentials(kiwi_config)
tester.perform_all_tests()
tester.upload_all_test_results()

```
