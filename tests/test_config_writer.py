# type: ignore
from pathlib import Path

import pytest
import yaml

from awsmp._api import ConfigWriter


@pytest.fixture(scope="function")
def written_yaml(tmp_path):
    config = {
        "offer": {
            "instance_types": [
                {"name": "a2.large", "yearly": "1.0", "hourly": "1.0", "vcpus": "2"},
                {"name": "a2.metal", "yearly": "2.0", "hourly": "2.0", "vcpus": "2"},
                {"name": "a1.large", "yearly": "0.0", "hourly": "0.0", "vcpus": "2"},
            ]
        }
    }
    path = tmp_path / "awsmp_config.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f)
    return path


@pytest.fixture(scope="function")
def read_config_file(written_yaml) -> ConfigWriter:
    c = ConfigWriter(written_yaml)
    c.read()
    return c


class TestConfigWriterSuite:
    def test_should_be_able_to_render_yaml_as_dict(self, written_yaml: Path):
        writer = ConfigWriter(written_yaml.absolute())
        writer._awsmp_config = {"some_config": {}}
        assert writer._to_dict() == {"some_config": {}}
        # get_updated

    def test_read_should_raise_on_invalid_path(self, written_yaml: Path):
        written_yaml.unlink()
        path = str(written_yaml.absolute())
        with pytest.raises(FileNotFoundError) as ex:
            ConfigWriter(path).read()
        assert f"Could not find awsmp config file {path}." in str(ex)

    def test_should_be_able_to_read_input_config(self, written_yaml: Path):
        writer = ConfigWriter(written_yaml.absolute())
        writer.read()
        assert writer._awsmp_config == {
            "offer": {
                "instance_types": [
                    {"name": "a2.large", "yearly": "1.0", "hourly": "1.0", "vcpus": "2"},
                    {"name": "a2.metal", "yearly": "2.0", "hourly": "2.0", "vcpus": "2"},
                    {"name": "a1.large", "yearly": "0.0", "hourly": "0.0", "vcpus": "2"},
                ]
            }
        }

    def test_should_be_able_to_insert_new_instance_type(self, read_config_file: ConfigWriter):
        new_type = {"name": "a2.xlarge", "hourly": "1.0", "yearly": "2.0", "vcpus": "2"}
        read_config_file.insert(new_type)
        assert read_config_file._awsmp_config == {
            "offer": {
                "instance_types": [
                    {"name": "a2.large", "yearly": "1.0", "hourly": "1.0", "vcpus": "2"},
                    {"name": "a2.metal", "yearly": "2.0", "hourly": "2.0", "vcpus": "2"},
                    {"name": "a1.large", "yearly": "0.0", "hourly": "0.0", "vcpus": "2"},
                    new_type,
                ]
            }
        }

    def test_should_be_able_to_replace_existing_type(self, read_config_file: ConfigWriter):
        new_type = {"name": "a2.large", "hourly": "1.0", "yearly": "1.0", "vcpus": "100"}
        read_config_file.insert(new_type)
        assert read_config_file._awsmp_config == {
            "offer": {
                "instance_types": [
                    new_type,
                    {"name": "a2.metal", "yearly": "2.0", "hourly": "2.0", "vcpus": "2"},
                    {"name": "a1.large", "yearly": "0.0", "hourly": "0.0", "vcpus": "2"},
                ]
            }
        }

    def test_should_be_able_to_write_config(self, read_config_file: ConfigWriter):
        read_config_file.write()
        assert Path(read_config_file.awsmp_config_file).exists()

    def test_written_config_file_should_be_sorted_by_instance_type(self, read_config_file: ConfigWriter):
        read_config_file.write()
        expected_config = {
            "offer": {
                "instance_types": [
                    {
                        "name": "a1.large",
                        "yearly": "0.0",
                        "hourly": "0.0",
                    },
                    {
                        "name": "a2.large",
                        "yearly": "1.0",
                        "hourly": "1.0",
                    },
                    {
                        "name": "a2.metal",
                        "yearly": "2.0",
                        "hourly": "2.0",
                    },
                ]
            }
        }

        with open(read_config_file.awsmp_config_file, "r") as f:
            output = yaml.load(f, Loader=yaml.FullLoader)
        assert output == expected_config
