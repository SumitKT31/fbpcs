# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-strict

import os
import random
import time
from typing import Iterable
from unittest import TestCase
from unittest.mock import patch, MagicMock, Mock

from fbpcs.pc_pre_validation.constants import (
    INPUT_DATA_VALIDATOR_NAME,
    INPUT_DATA_TMP_FILE_PATH,
    PA_FIELDS,
    PL_FIELDS,
)
from fbpcs.pc_pre_validation.enums import ValidationResult
from fbpcs.pc_pre_validation.input_data_validator import InputDataValidator
from fbpcs.pc_pre_validation.validation_report import ValidationReport
from fbpcs.private_computation.entity.cloud_provider import CloudProvider

# Name the file randomly in order to avoid failures when the tests run concurrently
TEST_FILENAME = f"test-input-data-validation-{random.randint(0, 1000000)}.csv"
TEST_CLOUD_PROVIDER: CloudProvider = CloudProvider.AWS
TEST_INPUT_FILE_PATH = f"s3://test-bucket/{TEST_FILENAME}"
TEST_REGION = "us-west-2"
TEST_TIMESTAMP: float = time.time()
TEST_TEMP_FILEPATH = f"{INPUT_DATA_TMP_FILE_PATH}/{TEST_FILENAME}-{TEST_TIMESTAMP}"


class TestInputDataValidator(TestCase):
    def setUp(self) -> None:
        with open(TEST_TEMP_FILEPATH, "a") as file:
            file.write("")

    def tearDown(self) -> None:
        os.remove(TEST_TEMP_FILEPATH)

    def write_lines_to_file(self, lines: Iterable[bytes]) -> None:
        with open(TEST_TEMP_FILEPATH, "wb") as tmp_csv_file:
            tmp_csv_file.writelines(lines)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    def test_initializing_the_validation_runner_fields(
        self, mock_storage_service: Mock
    ) -> None:
        access_key_id = "id1"
        access_key_data = "data2"
        constructed_storage_service = MagicMock()
        mock_storage_service.__init__(return_value=constructed_storage_service)

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH,
            TEST_CLOUD_PROVIDER,
            TEST_REGION,
            access_key_id,
            access_key_data,
        )

        mock_storage_service.assert_called_with(
            TEST_REGION, access_key_id, access_key_data
        )
        self.assertEqual(validator._storage_service, constructed_storage_service)
        self.assertEqual(validator._input_file_path, TEST_INPUT_FILE_PATH)
        self.assertEqual(validator._cloud_provider, TEST_CLOUD_PROVIDER)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    def test_run_validations_copy_failure(self, storage_service_mock: Mock) -> None:
        exception_message = "failed to copy"
        expected_report = ValidationReport(
            validation_result=ValidationResult.FAILED,
            validator_name=INPUT_DATA_VALIDATOR_NAME,
            message=f"File: {TEST_INPUT_FILE_PATH} failed validation. Error: Failed to download the input file. Please check the file path and its permission.\n\t{exception_message}",
            details={
                "rows_processed_count": 0,
            },
        )
        storage_service_mock.__init__(return_value=storage_service_mock)
        storage_service_mock.copy.side_effect = Exception(exception_message)

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, TEST_CLOUD_PROVIDER, TEST_REGION
        )
        report = validator.validate()

        self.assertEqual(report, expected_report)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    @patch("fbpcs.pc_pre_validation.input_data_validator.time")
    def test_run_validations_success_for_pl_fields(
        self, time_mock: Mock, _storage_service_mock: Mock
    ) -> None:
        time_mock.time.return_value = TEST_TIMESTAMP
        lines = [
            b"id_,value,event_timestamp\n",
            b"abcd/1234+WXYZ=,100,1645157987\n",
            b"abcd/1234+WXYZ=,100,1645157987\n",
            b"abcd/1234+WXYZ=,100,1645157987\n",
        ]
        self.write_lines_to_file(lines)
        expected_report = ValidationReport(
            validation_result=ValidationResult.SUCCESS,
            validator_name=INPUT_DATA_VALIDATOR_NAME,
            message=f"File: {TEST_INPUT_FILE_PATH} completed validation successfully",
            details={
                "rows_processed_count": 3,
            },
        )

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, TEST_CLOUD_PROVIDER, TEST_REGION
        )
        report = validator.validate()

        self.assertEqual(report, expected_report)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    @patch("fbpcs.pc_pre_validation.input_data_validator.time")
    def test_run_validations_success_for_pa_fields(
        self, time_mock: Mock, _storage_service_mock: Mock
    ) -> None:
        time_mock.time.return_value = TEST_TIMESTAMP
        cloud_provider = CloudProvider.AWS
        lines = [
            b"id_,conversion_value,conversion_timestamp,conversion_metadata\n",
            b"abcd/1234+WXYZ=,,1645157987,0\n",
            b"abcd/1234+WXYZ=,,1645157987,0\n",
            b"abcd/1234+WXYZ=,$20,1645157987,0\n",
        ]
        self.write_lines_to_file(lines)
        expected_report = ValidationReport(
            validation_result=ValidationResult.SUCCESS,
            validator_name=INPUT_DATA_VALIDATOR_NAME,
            message=f"File: {TEST_INPUT_FILE_PATH} completed validation successfully, with some warnings.",
            details={
                "rows_processed_count": 3,
                "validation_warnings": {
                    "conversion_value": {
                        "empty_count": 2,
                        "bad_format_count": 1,
                    },
                },
            },
        )

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, cloud_provider, TEST_REGION
        )
        report = validator.validate()

        self.assertEqual(report, expected_report)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    @patch("fbpcs.pc_pre_validation.input_data_validator.time")
    def test_run_validations_errors_when_input_data_fields_not_found(
        self, time_mock: Mock, _storage_service_mock: Mock
    ) -> None:
        exception_message = f"Failed to parse the header row. The header row fields must be either: {PL_FIELDS} or: {PA_FIELDS}"
        time_mock.time.return_value = TEST_TIMESTAMP
        lines = [
            b"bad,header,row\n",
            b"1,2,3\n",
            b"4,5,6\n",
        ]
        self.write_lines_to_file(lines)
        expected_report = ValidationReport(
            validation_result=ValidationResult.FAILED,
            validator_name=INPUT_DATA_VALIDATOR_NAME,
            message=f"File: {TEST_INPUT_FILE_PATH} failed validation. Error: {exception_message}",
            details={
                "rows_processed_count": 0,
            },
        )

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, TEST_CLOUD_PROVIDER, TEST_REGION
        )
        report = validator.validate()

        self.assertEqual(report, expected_report)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    @patch("fbpcs.pc_pre_validation.input_data_validator.time")
    def test_run_validations_errors_when_there_is_no_header_row(
        self, time_mock: Mock, _storage_service_mock: Mock
    ) -> None:
        time_mock.time.return_value = TEST_TIMESTAMP
        expected_report = ValidationReport(
            validation_result=ValidationResult.FAILED,
            validator_name=INPUT_DATA_VALIDATOR_NAME,
            message=f"File: {TEST_INPUT_FILE_PATH} failed validation. Error: The header row was empty.",
            details={
                "rows_processed_count": 0,
            },
        )

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, TEST_CLOUD_PROVIDER, TEST_REGION
        )
        report = validator.validate()

        self.assertEqual(report, expected_report)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    @patch("fbpcs.pc_pre_validation.input_data_validator.time")
    def test_run_validations_errors_when_the_line_ending_is_unsupported(
        self, time_mock: Mock, _storage_service_mock: Mock
    ) -> None:
        exception_message = "Detected an unexpected line ending. The only supported line ending is '\\n'"
        time_mock.time.return_value = TEST_TIMESTAMP
        lines = [
            b"id_,value,event_timestamp\n",
            b"abcd/1234+WXYZ=,100,1645157987\r\n",
            b"abcd/1234+WXYZ=,100,1645157987\r\n",
        ]
        self.write_lines_to_file(lines)
        expected_report = ValidationReport(
            validation_result=ValidationResult.FAILED,
            validator_name=INPUT_DATA_VALIDATOR_NAME,
            message=f"File: {TEST_INPUT_FILE_PATH} failed validation. Error: {exception_message}",
            details={
                "rows_processed_count": 0,
            },
        )

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, TEST_CLOUD_PROVIDER, TEST_REGION
        )
        report = validator.validate()

        self.assertEqual(report, expected_report)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    @patch("fbpcs.pc_pre_validation.input_data_validator.time")
    def test_run_validations_reports_for_pl_when_row_values_are_empty(
        self, time_mock: Mock, _storage_service_mock: Mock
    ) -> None:
        time_mock.time.return_value = TEST_TIMESTAMP
        lines = [
            b"id_,value,event_timestamp\n",
            b",100,1645157987\n",
            b"abcd/1234+WXYZ=,,1645157987\n",
            b"abcd/1234+WXYZ=,100,\n",
            b"abcd/1234+WXYZ=,,\n",
            b"abcd/1234+WXYZ=,100,\n",
            b"abcd/1234+WXYZ=,100,\n",
        ]
        self.write_lines_to_file(lines)
        error_fields = "event_timestamp, id_"
        expected_report = ValidationReport(
            validation_result=ValidationResult.FAILED,
            validator_name=INPUT_DATA_VALIDATOR_NAME,
            message=f"File: {TEST_INPUT_FILE_PATH} failed validation, with errors on '{error_fields}'.",
            details={
                "rows_processed_count": 6,
                "validation_errors": {
                    "id_": {
                        "empty_count": 1,
                    },
                    "event_timestamp": {
                        "empty_count": 4,
                    },
                },
                "validation_warnings": {
                    "value": {
                        "empty_count": 2,
                    },
                },
            },
        )

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, TEST_CLOUD_PROVIDER, TEST_REGION
        )
        report = validator.validate()

        self.assertEqual(report, expected_report)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    @patch("fbpcs.pc_pre_validation.input_data_validator.time")
    def test_run_validations_reports_for_pa_when_row_values_are_empty(
        self, time_mock: Mock, _storage_service_mock: Mock
    ) -> None:
        time_mock.time.return_value = TEST_TIMESTAMP
        lines = [
            b"id_,conversion_value,conversion_timestamp,conversion_metadata\n",
            b"abcd/1234+WXYZ=,100,1645157987,\n",
            b"abcd/1234+WXYZ=,,1645157987,\n",
            b"abcd/1234+WXYZ=,100,,0\n",
            b"abcd/1234+WXYZ=,,,0\n",
            b"abcd/1234+WXYZ=,100,,0\n",
            b"abcd/1234+WXYZ=,100,,\n",
        ]
        self.write_lines_to_file(lines)
        error_fields = "conversion_timestamp"
        expected_report = ValidationReport(
            validation_result=ValidationResult.FAILED,
            validator_name=INPUT_DATA_VALIDATOR_NAME,
            message=f"File: {TEST_INPUT_FILE_PATH} failed validation, with errors on '{error_fields}'.",
            details={
                "rows_processed_count": 6,
                "validation_errors": {
                    "conversion_timestamp": {
                        "empty_count": 4,
                    },
                },
                "validation_warnings": {
                    "conversion_value": {
                        "empty_count": 2,
                    },
                    "conversion_metadata": {
                        "empty_count": 3,
                    },
                },
            },
        )

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, TEST_CLOUD_PROVIDER, TEST_REGION
        )
        report = validator.validate()

        self.assertEqual(report, expected_report)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    @patch("fbpcs.pc_pre_validation.input_data_validator.time")
    def test_run_validations_reports_for_pl_when_row_values_are_not_valid(
        self, time_mock: Mock, _storage_service_mock: Mock
    ) -> None:
        time_mock.time.return_value = TEST_TIMESTAMP
        lines = [
            b"id_,value,event_timestamp\n",
            b"ab...,100,1645157987\n",
            b"abcd/1234+WXYZ=,test,ts2\n",
            b"abcd/1234+WXYZ=,100,1645157987\n",
            b"abcd/1234+WXYZ=,,*\n",
            b"abcd/1234+WXYZ=,,&\n",
        ]
        self.write_lines_to_file(lines)
        error_fields = "event_timestamp, id_"
        expected_report = ValidationReport(
            validation_result=ValidationResult.FAILED,
            validator_name=INPUT_DATA_VALIDATOR_NAME,
            message=f"File: {TEST_INPUT_FILE_PATH} failed validation, with errors on '{error_fields}'.",
            details={
                "rows_processed_count": 5,
                "validation_errors": {
                    "id_": {
                        "bad_format_count": 1,
                    },
                    "event_timestamp": {
                        "bad_format_count": 3,
                    },
                },
                "validation_warnings": {
                    "value": {
                        "bad_format_count": 1,
                        "empty_count": 2,
                    },
                },
            },
        )

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, TEST_CLOUD_PROVIDER, TEST_REGION
        )
        report = validator.validate()

        self.assertEqual(report, expected_report)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    @patch("fbpcs.pc_pre_validation.input_data_validator.time")
    def test_run_validations_reports_for_pa_when_row_values_are_not_valid(
        self, time_mock: Mock, _storage_service_mock: Mock
    ) -> None:
        time_mock.time.return_value = TEST_TIMESTAMP
        lines = [
            b"id_,conversion_value,conversion_timestamp,conversion_metadata\n",
            b"abcd/1234+WXYZ=,$100,1645157987,\n",
            b" ! ,100,1645157987,\n",
            b"_,100,...,0\n",
            b",100,...,data\n",
        ]
        self.write_lines_to_file(lines)
        error_fields = "conversion_timestamp, id_"
        expected_report = ValidationReport(
            validation_result=ValidationResult.FAILED,
            validator_name=INPUT_DATA_VALIDATOR_NAME,
            message=f"File: {TEST_INPUT_FILE_PATH} failed validation, with errors on '{error_fields}'.",
            details={
                "rows_processed_count": 4,
                "validation_errors": {
                    "id_": {
                        "bad_format_count": 2,
                        "empty_count": 1,
                    },
                    "conversion_timestamp": {
                        "bad_format_count": 2,
                    },
                },
                "validation_warnings": {
                    "conversion_metadata": {"bad_format_count": 1, "empty_count": 2},
                    "conversion_value": {
                        "bad_format_count": 1,
                    },
                },
            },
        )

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, TEST_CLOUD_PROVIDER, TEST_REGION
        )
        report = validator.validate()
        self.assertEqual(report, expected_report)

    @patch("fbpcs.pc_pre_validation.input_data_validator.S3StorageService")
    @patch(
        "fbpcs.pc_pre_validation.input_data_validator.InputDataValidationIssues.count_empty_field"
    )
    @patch("fbpcs.pc_pre_validation.input_data_validator.time")
    def test_run_validations_an_unhandled_exception_propagates_to_the_caller(
        self,
        time_mock: Mock,
        count_empty_field_mock: Mock,
        _storage_service_mock: Mock,
    ) -> None:
        time_mock.time.return_value = TEST_TIMESTAMP
        expected_exception_message = "bug in the logic"
        lines = [
            b"id_,value,event_timestamp\n",
            b"abcd/1234+WXYZ=,,1645157987\n",
        ]
        self.write_lines_to_file(lines)
        count_empty_field_mock.side_effect = Exception(expected_exception_message)

        validator = InputDataValidator(
            TEST_INPUT_FILE_PATH, TEST_CLOUD_PROVIDER, TEST_REGION
        )
        report = validator.validate()

        self.assertEqual(report.validation_result, ValidationResult.SUCCESS)
        self.assertRegex(
            report.message,
            f"WARNING: {INPUT_DATA_VALIDATOR_NAME} threw an unexpected error: {expected_exception_message}",
        )
