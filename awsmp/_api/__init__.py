import yaml

from .. import sort_instance_types, yaml_utils
from ..models import InstanceTypePricing, Offer


class ConfigWriter:
    """Convenience class for rewriting awsmp config
    ConfigWriter rebuilds an awsmp config with input InstanceTypes.
    The resulting yaml has instance types ordered by relative size.
    """

    def __init__(self, awsmp_config_file: str):
        self.awsmp_config_file: str = awsmp_config_file
        self._awsmp_config: Offer = {}
        self._instance_type_indexes: dict[str, int] = {}

    def _to_dict(self) -> Offer:
        return self._awsmp_config

    def read(self) -> None:
        try:
            with open(self.awsmp_config_file, "r") as f:
                self._awsmp_config = yaml.load(f, Loader=yaml.FullLoader)
        except FileNotFoundError as ex:
            raise FileNotFoundError(f"Could not find awsmp config file {self.awsmp_config_file}.") from ex

    def insert(self, instance_type: InstanceTypePricing) -> None:
        instance_types = self._get_instance_types()
        if not self._instance_type_indexes:
            for i, v in enumerate(instance_types):
                self._instance_type_indexes[v["name"]] = i

        instance_type_name = instance_type["name"]
        if instance_type_name in self._instance_type_indexes:
            index = self._instance_type_indexes[instance_type_name]
            instance_types[index] = instance_type
        else:
            instance_types.append(instance_type)

    def _get_instance_types(self) -> list[InstanceTypePricing]:
        return self._awsmp_config["offer"]["instance_types"]

    def write(self) -> None:
        instance_types = self._get_instance_types()
        for i in instance_types:
            if "vcpus" in i:
                del i["vcpus"]  # type: ignore
        with open(self.awsmp_config_file, "w") as f:
            self._awsmp_config["offer"]["instance_types"] = sort_instance_types(instance_types)
            with open(self.awsmp_config_file, "w") as f:
                yaml_utils.dump(self._awsmp_config, f)
