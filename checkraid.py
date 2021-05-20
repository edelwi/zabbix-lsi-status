#!/bin/env python3

import re
import subprocess
import unicodedata
from os import remove, listdir, makedirs
from os.path import exists, join, isfile

LLD_JSON_PATH = '/var/local/lsi_zabbix'
LLD_METRICS_PATH = '/var/local/lsi_zabbix/metrics'  # Be careful all files in this directory deleted automatically.
LLD_CONTROLLERS = 'controllers.json'
LLD_ARRAYS = 'arrays.json'
LLD_DISKS = 'disks.json'

MEGACLI = '/usr/bin/MegaCli64'  # full path to MegaCli64

ADAPTER_INFO_CLI = [MEGACLI, '-AdpAllinfo', '-aALL']
DRIVES_INFO_CLI = [MEGACLI, '-LdPdInfo', '-aALL']

ARRAY_NAME_PATT = re.compile(r'(?P<array_name>Virtual Drive\s+#\d{1,2})')
PD_NAME_PATT = re.compile(r'(?P<pd_name>Physical Drive\s+#\d{1,2})')

ADAPTER_PATT = re.compile(r'^(?P<adp_name>Adapter\s+#(?P<adp_num>\d{1,2}))$')
VIRTUAL_DRIVE_PATT = re.compile(r'^Virtual Drive:\s+(?P<vd_id>\d{1,2})\s+\(Target Id:\s+(?P<tgt_id>\d{1,2})\)$')
PHYSICAL_DRIVE_PATT = re.compile(r'PD:\s+(?P<pd_id>\d{1,2})\s+Information$')
PARAM_PATT = re.compile(r'^\s*(?P<key>[^:]+)\s*:\s*(?P<value>.*)$')


# Data processing pipe.
def pipe(data, *fseq):
    for fn in fseq:
        data = fn(data)
    return data


def debug(data):
    print(data)
    return data


def run_command(cli: list) -> str:
    """Function for running command and get detailed output about controllers."""
    p = subprocess.Popen(
        cli,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    (output, err) = p.communicate()
    if err:
        raise ValueError(f'hpsa call error {err}')
    return output


def create_dir(full_dir_path):
    if not exists(full_dir_path):
        makedirs(full_dir_path)


def remove_file(full_file_name):
    if exists(full_file_name):
        remove(full_file_name)


def remove_all_metrics_files(data):
    """Function to remove all files in LLD_METRICS_PATH directory."""
    if exists(LLD_METRICS_PATH):
        [remove(join(LLD_METRICS_PATH, _)) for _ in listdir(LLD_METRICS_PATH) if isfile(join(LLD_METRICS_PATH, _))]
    return data


# from https://stackoverflow.com/questions/4814040/allowed-characters-in-filename
def clean_name(name, replace_space_with=None):
    """
    Remove invalid file name chars from the specified name

    :param name: the file name
    :param replace_space_with: if not none replace space with this string
    :return: a valid name for Win/Mac/Linux
    """

    # ref: https://en.wikipedia.org/wiki/Filename
    # ref: https://stackoverflow.com/questions/4814040/allowed-characters-in-filename
    # No control chars, no: /, \, ?, %, *, :, |, ", <, >

    # remove control chars
    name = ''.join(ch for ch in name if unicodedata.category(ch)[0] != 'C')

    cleaned_name = re.sub(r'[/\\?%*:|"<>]', '_', name)
    if replace_space_with is not None:
        return cleaned_name.replace(' ', replace_space_with)
    return cleaned_name


def convert_to_dict(stdout: str):
    lines = stdout.decode('utf-8').split("\n")
    lines = list(filter(None, lines))
    info_dict = _split_by_adapters(lines)
    return info_dict


def convert_drive_info_to_dict(stdout: str):
    lines = stdout.decode('utf-8').split("\n")
    lines = list(filter(None, lines))
    info_dict = _split_drive_info_by_adapters(lines)
    return info_dict


def _split_by_params(params: list) -> dict:
    params_dict = {}
    for item in params:
        if isinstance(item, str):
            match = re.search(PARAM_PATT, item)
            if match:
                param_key = match.groupdict()['key'].strip()
                param_value = match.groupdict()['value'].strip()
                if param_key != 'Port' and param_value != 'Address':
                    params_dict[param_key] = param_value
    return params_dict


def _split_by_sections(proto_section: list):
    sections = {}
    patams_delimiter = '                ================'
    indexes = [i for i, e in enumerate(proto_section) if e == patams_delimiter]
    start_index = 0
    for index in indexes:
        if start_index == 0:
            start_index = index
            continue
        section_name = str(proto_section[start_index - 1]).strip(' :')
        sections[section_name] = _split_by_params(proto_section[start_index + 1:index])
        start_index = index
    else:
        index = len(proto_section) - 1
        section_name = str(proto_section[start_index - 1]).strip()
        sections[section_name] = _split_by_params(proto_section[start_index + 1:index])
    return sections


def _split_by_adapters(lines: list):
    adapters = {}
    adapter_delimiter = '=' * 78
    indexes = [i for i, e in enumerate(lines) if e == adapter_delimiter]
    start_index = 0
    for index in indexes:
        if start_index == 0:
            start_index = index
            continue
        adapter_name = lines[start_index - 1].strip()
        adapters[adapter_name] = _split_by_sections(lines[start_index + 1:index])
        start_index = index
    else:
        index = len(lines) - 1
        adapter_name = lines[start_index - 1].strip()
        adapters[adapter_name] = _split_by_sections(lines[start_index + 1:index])
    return adapters


def _split_drive_info_by_adapters(lines: list):
    adapters = {}
    indexes = [i for i, e in enumerate(lines) if re.search(ADAPTER_PATT, e)]
    start_index = 0
    for index in indexes:
        if start_index == 0:
            start_index = index
            adapters = _split_by_params(lines[0:start_index])
            continue
        adapters[lines[start_index]] = _split_drive_info_by_vd(lines[start_index + 1:index])
        start_index = index
    else:
        index = len(lines) - 1
        adapters[lines[start_index]] = _split_drive_info_by_vd(lines[start_index + 1:index])
    return adapters


def _split_drive_info_by_vd(lines: list):
    virt_drives = {}
    indexes = [i for i, e in enumerate(lines) if re.search(VIRTUAL_DRIVE_PATT, e)]
    start_index = 0

    for index in indexes:
        if start_index == 0:
            start_index = index
            virt_drives = _split_by_params(lines[0:start_index])
            continue
        match = re.search(VIRTUAL_DRIVE_PATT, lines[start_index])
        if match:
            vd_name = f'Virtual Drive #{match.groupdict()["vd_id"]}'
            virt_drives[vd_name] = _split_drive_info_by_pd(lines[start_index + 1:index])
        start_index = index
    else:
        index = len(lines)
        match = re.search(VIRTUAL_DRIVE_PATT, lines[start_index])
        if match:
            vd_name = f'Virtual Drive #{match.groupdict()["vd_id"]}'
            virt_drives[vd_name] = _split_drive_info_by_pd(lines[start_index + 1:index])
    return virt_drives


def _split_drive_info_by_pd(lines: list):
    physical_drives = {}
    indexes = [i for i, e in enumerate(lines) if re.search(PHYSICAL_DRIVE_PATT, e)]
    start_index = 0
    for index in indexes:
        if start_index == 0:
            start_index = index
            physical_drives = _split_by_params(lines[0:start_index])
            continue
        match = re.search(PHYSICAL_DRIVE_PATT, lines[start_index])
        if match:
            pd_name = f'Physical Drive #{match.groupdict()["pd_id"]}'
            physical_drives[pd_name] = _split_by_params(lines[start_index + 1:index])
        start_index = index
    else:
        index = len(lines)
        match = re.search(PHYSICAL_DRIVE_PATT, lines[start_index])
        if match:
            pd_name = f'Physical Drive #{match.groupdict()["pd_id"]}'
            physical_drives[pd_name] = _split_by_params(lines[start_index + 1:index])
    return physical_drives


def pretty_print(info_dict, level=0):
    """Recursive function for printing dictionary with raid detailed information."""

    indent = ' ' * 4
    current_level = level
    for k, v in info_dict.items():
        if isinstance(v, str) or v is None:
            print(f"{indent * current_level}{k}: {v}")
        else:
            print()
            print(f"{indent * current_level}{k}:")
            pretty_print(v, level=current_level + 1)


def lld_discovery_controllers(data):
    """Function for create LLD json with information about controllers."""

    file_ = LLD_CONTROLLERS
    discovery_file = join(LLD_JSON_PATH, file_)
    create_dir(LLD_JSON_PATH)
    remove_file(discovery_file)
    controllers = data.keys()
    json_data = ''
    for item in controllers:
        json_data = json_data + f'{{"{{#CTRLNAME}}":"{clean_name(item)}"}},'
    json_data = json_data[:-1]
    with open(discovery_file, 'w') as fl:
        print(f'{{"data":[{json_data}]}}', file=fl)
    return data


def lld_discovery_arrays(data):
    """Function for create LLD json with information about RAID arrays."""

    file_ = LLD_ARRAYS
    discovery_file = join(LLD_JSON_PATH, file_)
    create_dir(LLD_JSON_PATH)
    remove_file(discovery_file)
    json_data = ''
    for ctrl, ctrl_value in data.items():
        if isinstance(ctrl_value, dict):
            for ar_key, ar_value in ctrl_value.items():
                match = re.search(ARRAY_NAME_PATT, ar_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    json_data = json_data + f'{{"{{#CTRLNAME}}":"{clean_name(ctrl)}","' \
                                            f'{{#ARRAYNAME}}":"{clean_name(ar_name)}"}},'
                # else:
                #     print(ar_key)
    json_data = json_data[:-1]
    with open(discovery_file, 'w') as fl:
        print(f'{{"data":[{json_data}]}}', file=fl)
    return data


def lld_discovery_pds(data):
    """Function for create LLD json with information about RAID physical disks."""

    file_ = LLD_DISKS
    discovery_file = join(LLD_JSON_PATH, file_)
    create_dir(LLD_JSON_PATH)
    remove_file(discovery_file)
    json_data = ''
    for ctrl, ctrl_value in data.items():
        if isinstance(ctrl_value, dict):
            for ar_key, ar_value in ctrl_value.items():
                match = re.search(ARRAY_NAME_PATT, ar_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    for pd_key, pd_value in ar_value.items():
                        match2 = re.search(PD_NAME_PATT, pd_key)
                        if match2:
                            pd_name = match2.groupdict()['pd_name']
                            json_data = json_data + f'{{"{{#CTRLNAME}}":"{clean_name(ctrl)}","{{#ARRAYNAME}}":"' \
                                                    f'{clean_name(ar_name)}","{{#PDNAME}}":"{clean_name(pd_name)}"}},'
    json_data = json_data[:-1]
    with open(discovery_file, 'w') as fl:
        print(f'{{"data":[{json_data}]}}', file=fl)
    return data


def get_ctrl_metrics(data):
    """Function for create controllers metrics files."""

    create_dir(LLD_METRICS_PATH)
    for ctrl, ctrl_value in data.items():
        file_name = clean_name(ctrl)
        full_file_name = join(LLD_METRICS_PATH, file_name)
        with open(full_file_name, 'w') as fl:
            if isinstance(ctrl_value, dict):
                for metric, value in ctrl_value.items():
                    if isinstance(value, str):
                        print(f"{metric}={value}", file=fl)
    return data


def get_ctrl_sub_metrics(data):
    """Function for create controllers metrics files."""

    create_dir(LLD_METRICS_PATH)
    for ctrl, ctrl_value in data.items():
        file_name = clean_name(ctrl)
        full_file_name = join(LLD_METRICS_PATH, file_name)
        with open(full_file_name, 'w') as fl:
            if isinstance(ctrl_value, dict):
                for ctl_cat, ctl_cat_val in ctrl_value.items():
                    if isinstance(ctl_cat_val, dict):
                        for metric, value in ctl_cat_val.items():
                            if isinstance(value, str):
                                print(f"{metric}={value}", file=fl)
    return data


def get_array_metrics(data):
    """Function for create RAID arrays metrics files."""

    create_dir(LLD_METRICS_PATH)
    for ctrl, ctrl_value in data.items():
        if isinstance(ctrl_value, dict):
            for ar_key, ar_value in ctrl_value.items():
                match = re.search(ARRAY_NAME_PATT, ar_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    file_name = clean_name(f"{ctrl}__{ar_name}")
                    full_file_name = join(LLD_METRICS_PATH, file_name)
                    with open(full_file_name, 'w') as fl:
                        if isinstance(ar_value, dict):
                            for metric, value in ar_value.items():
                                if isinstance(value, str):
                                    print(f"{metric}={value}", file=fl)
    return data


def get_pd_metrics(data):
    """Function for create physical disks metrics files."""

    create_dir(LLD_METRICS_PATH)
    for ctrl, ctrl_value in data.items():
        if isinstance(ctrl_value, dict):
            for ar_key, ar_value in ctrl_value.items():
                match = re.search(ARRAY_NAME_PATT, ar_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    for pd_key, pd_value in ar_value.items():
                        match2 = re.search(PD_NAME_PATT, pd_key)
                        if match2:
                            pd_name = match2.groupdict()['pd_name']
                            file_name = clean_name(f"{ctrl}__{ar_name}__{pd_name}")
                            full_file_name = join(LLD_METRICS_PATH, file_name)
                            with open(full_file_name, 'w') as fl:
                                if isinstance(pd_value, dict):
                                    for metric, value in pd_value.items():
                                        if isinstance(value, str):
                                            print(f"{metric}={value}", file=fl)
    return data


if __name__ == '__main__':
    pipe(
        run_command(ADAPTER_INFO_CLI),
        convert_to_dict,
        remove_all_metrics_files,
        get_ctrl_sub_metrics,
        # pretty_print,
    )
    pipe(
        run_command(DRIVES_INFO_CLI),
        convert_drive_info_to_dict,
        lld_discovery_controllers,
        lld_discovery_arrays,
        lld_discovery_pds,
        get_array_metrics,
        get_pd_metrics,
        # pretty_print
    )
