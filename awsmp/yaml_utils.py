import yaml
from yaml.dumper import SafeDumper


class LiteralString(str):
    pass


def literal_str_representer(dumper, data):
    text = data if data.endswith("\n") else data + "\n"
    return dumper.represent_scalar("tag:yaml.org,2002:str", text, style="|")


class IndentListDumper(SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


yaml.add_representer(LiteralString, literal_str_representer, Dumper=IndentListDumper)


def dump(data, config):
    yaml.dump(data, config, Dumper=IndentListDumper, default_flow_style=False, indent=2, sort_keys=False)
