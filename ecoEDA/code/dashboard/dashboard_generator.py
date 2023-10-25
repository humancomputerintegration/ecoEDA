import argparse
import os, sys
sys.path.insert(1, '../util')
sys.path.insert(1, '../')
import json
from sexpdata import dumps

from Objectifier import Objectifier

from ecoEDA_data_utils import get_project_files_list
from ecoEDA_lib_utils import get_num_lib_cmpnts

def get_prj_data(file):
    sch = Objectifier(file)
    root = sch.root

    if len(root.xpath('/kicad_sch/title_block/title')) > 0:
        prj_name = root.xpath('/kicad_sch/title_block/title')[0].childs[0]
    else:
        prj_name = file.split("/")[-1].split(".kicad_sch")[0]

    sym_arr = root.xpath('/kicad_sch/symbol')
    total_num_compnts = 0
    src_dict = {}

    ecoEDA_count = 0
    for sym in sym_arr:
        source = ''
        if not sym.first_child.childs[0].startswith("power:"):
            total_num_compnts += 1
        sym_is_ecoEDA = False
        for property in sym.xpath('/symbol/property'):
            if property.first_child == 'ecoEDA':
                if property.childs[1] == 'Yes':
                    sym_is_ecoEDA = True
            elif property.first_child == 'Source':
                source = property.childs[1]

        if sym_is_ecoEDA:
            ecoEDA_count += 1
            if source != '':
                if source not in src_dict.keys():
                    src_dict[source] = 1
                else:
                    src_dict[source] += 1

    prj_data = {"Project": prj_name, "Sources": src_dict,
                "Total Components": total_num_compnts, "ecoEDA Components": ecoEDA_count}

    return prj_name, prj_data, ecoEDA_count

def get_prj_str_values(prj_list, prj_data):
    #Project list formatting
    prj_list_str = '['

    for prj in prj_list:
        prj_list_str += "\"" + prj + "\", "

    prj_list_str = prj_list_str[:-2] + "]"


    #Project Data formatting
    prj_data_str = '['

    for prj in prj_data:
        prj_data_str += "{"
        for key in prj.keys():
            if key == 'Project':
                prj_data_str += "\"" + key + "\": \"" + prj[key] + "\", "
            elif key == 'Total Components' or key == 'ecoEDA Components':
                prj_data_str += "\"" + key + "\": " + str(prj[key]) + ", "
            elif key == 'Sources':
                prj_data_str += "\"" + key + "\": {"
                for s_key in prj[key].keys():
                    prj_data_str += "\"" + s_key + "\": " + str(prj[key][s_key]) + ", "
                prj_data_str = prj_data_str[:-2] + "}, "
        prj_data_str = prj_data_str[:-2] + "}, "

    prj_data_str = prj_data_str[:-2] + "]"
    return prj_list_str, prj_data_str

def write_dashboard_data(num_projects, components_reused, components_in_lib, prj_list, prj_data):
    original_stdout = sys.stdout
    with open('./dashboard_data.js', 'w') as f:
        sys.stdout = f
        print("num_projects = "  + str(num_projects) + "\n" )
        print("components_reused = " + str(components_reused) + "\n" )
        print("components_in_lib = " + str(components_in_lib) + "\n" )
        print("prj_list = " + prj_list + "\n" )
        print("prj_data = " + prj_data + "\n" )
        sys.stdout = original_stdout

if __name__ == "__main__":
    with open('../ecoEDA_data.json', 'r') as f:
        ecoEDA_data = json.load(f)

    prj_files_list = get_project_files_list(ecoEDA_data)
    #prj_files_list = ["/Users/jasminelu/Downloads/Assignment7/jianingwei-hw7.kicad_sch"]

    num_projects = len(prj_files_list)
    num_lib_cmpnts = get_num_lib_cmpnts('../ecoEDA.kicad_sym')

    prj_data_all = []
    prj_list = []
    components_reused = 0

    for file in prj_files_list:
        prj_name, prj_data, ecoEDA_count = get_prj_data(file)
        prj_list.append(prj_name)
        prj_data_all.append(prj_data)
        components_reused += ecoEDA_count

    prj_list_str, prj_data_str = get_prj_str_values(prj_list, prj_data_all)
    write_dashboard_data(num_projects, components_reused, num_lib_cmpnts, prj_list_str, prj_data_str)
