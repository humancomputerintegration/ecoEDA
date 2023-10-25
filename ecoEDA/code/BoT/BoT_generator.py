import argparse
import os, sys
sys.path.insert(1, '../util')

import json
from sexpdata import dumps

from Objectifier import Objectifier

# from file, retrieve relevant data for generating Bill of Teardowns
def get_BoT_data(file):
    sch = Objectifier(file)
    root = sch.root

    # retrieve project name
    if len(root.xpath('/kicad_sch/title_block/title')) > 0:
        prj_name = root.xpath('/kicad_sch/title_block/title')[0].childs[0]
    else:
        prj_name = file.split("/")[-1].split(".kicad_sch")[0]

    # get symbol information
    sch_sym_data = []
    sym_arr = root.xpath('/kicad_sch/symbol')
    for sym in sym_arr:
        sym_obj = {'Component Name': '', 'uuid': '', 'Reference': ''}
        lib_id = sym.first_child.childs[0]

        sym_is_ecoEDA = False
        for property in sym.xpath('/symbol/property'):
            if property.first_child == 'ecoEDA':
                if property.childs[1] == 'Yes':
                    sym_is_ecoEDA = True

        if sym_is_ecoEDA:
            sym_obj['Component Name'] = lib_id
            sym_obj['uuid'] = dumps(sym.xpath('/symbol/uuid')[0].first_child)

            for path in root.xpath('/kicad_sch/symbol_instances/path'):
                if path.first_child[1:] == sym_obj['uuid']:
                    sym_obj['Reference'] = path.childs[1].first_child

            sch_sym_data.append(sym_obj)

    # get symbol library information
    lib_sym_instances = {}
    lib_ref_instances = {}

    for sym in sch_sym_data:
        if sym['Component Name'] in lib_sym_instances.keys():
            lib_sym_instances[sym['Component Name']].append(sym['uuid'])
            lib_ref_instances[sym['Component Name']].append(sym['Reference'])
        else:
            lib_sym_instances[sym['Component Name']] = [sym['uuid']]
            lib_ref_instances[sym['Component Name']] = [sym['Reference']]

    sources_list = []
    sources_data = []

    for sym in lib_sym_instances.keys():
        for sch_lib_sym in root.xpath('/kicad_sch/lib_symbols/symbol'):
            if sch_lib_sym.first_child == sym:
                source = ''
                teardown_link = ''
                footprint = ''
                value = ''
                quantity = ''
                pcb_designator = ''
                for property in sch_lib_sym.childs[1:]:
                    if property.first_child == 'Source':
                        source = property.childs[1]
                    elif property.first_child == 'Teardown Link':
                        teardown_link = property.childs[1]
                    elif property.first_child == 'Value':
                        value = property.childs[1]
                    elif property.first_child == 'Footprint':
                        footprint = property.childs[1]
                    elif property.first_child == 'Quantity':
                        quantity = property.childs[1]
                    elif property.first_child == 'PCB Designator':
                        pcb_designator = property.childs[1]

                if quantity == '':
                    quantity = 1
                component_name = sym
                if ":" in component_name:
                    component_name = sym.split(":")[1]
                component_data_obj = {"Component Name": component_name,
                                      "References": lib_ref_instances[sym],
                                      "Value": value,
                                      "Footprint": footprint,
                                      "Quantity": quantity,
                                      "PCB Designator": pcb_designator,
                                      "Notes": ""}
                if source not in sources_list:
                    sources_list.append(source)
                    src_data_obj = {"Source": source,
                                    "Num Components": len(lib_sym_instances[sym]),
                                    "Torn Down": False,
                                    "Teardown Link": teardown_link,
                                    "Components": [component_data_obj]}
                    sources_data.append(src_data_obj)
                else:
                    for source_obj in sources_data:
                        if source_obj["Source"] == source:
                            source_obj["Components"].append(component_data_obj)
                            source_obj["Num Components"] = source_obj["Num Components"] + len(lib_sym_instances[sym])


    return prj_name, sources_list, sources_data

# write Bill of Teardown information to js file
def write_BoT_data(prj_name_str, src_list_str, src_data_str):
    original_stdout = sys.stdout
    with open('./BoT_data.js', 'w') as f:
        sys.stdout = f
        print("BoT_project_name = " + "\"" + prj_name_str + "\"\n" )
        print("BoT_Sources_List = " + src_list_str + "\n" )
        print("BoT_Sources_Data = " + src_data_str + "\n" )
        sys.stdout = original_stdout

# format the Bill of Teardown information as readable for the file
def format_BoT_data(prj_name, src_list, src_data):

    #FORMAT SOURCES LIST
    src_list_str = "["

    for src in src_list:
        src_list_str += ("\"" + src + "\", ")

    src_list_str = src_list_str[:-2] + "]"


    #FORMAT SOURCES DATA
    src_data_str = "["
    for src in src_data:
        src_data_str += "{"
        for key in src.keys():
            if key == 'Source':
                src_data_str += "\"" + key + "\": \"" + src[key] + "\", "
            elif key == 'Num Components':
                src_data_str += "\"" + key + "\": " + str(src[key]) + ", "
            elif key == 'Torn Down':
                if src[key]:
                    src_data_str += "\"" + key + "\": true, "
                else:
                    src_data_str += "\"" + key + "\": false, "
            elif key == 'Teardown Link':
                src_data_str += "\"" + key + "\": \"" + src[key] + "\", "
            elif key == 'Components':
                src_data_str += "\"" + key + "\": ["
                for cmpn_obj in src[key]:
                    src_data_str += "{"
                    for c_key in cmpn_obj.keys():
                        if c_key == 'References':
                            references = ""
                            for ref in cmpn_obj[c_key]:
                                references += ref + ","
                            references = references[:-1]
                            src_data_str += "\"" + c_key + "\": \"" + references + "\", "
                        elif c_key == 'Quantity':
                            src_data_str += "\"" + c_key + "\": " + str(cmpn_obj[c_key]) + ", "
                        else:
                            src_data_str += "\"" + c_key + "\": \"" + cmpn_obj[c_key] + "\", "
                    src_data_str = src_data_str[:-2] + "}, "
                src_data_str = src_data_str[:-2] + "]"
        src_data_str += "}, "
    src_data_str = src_data_str[:-2]  + "]"

    return prj_name, src_list_str, src_data_str

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="",
      help="The kicad schematic file to generate BoT for")
    args = parser.parse_args()

    if(args.file != ""):
        file = args.file
        prj_name, src_list, src_data = get_BoT_data(file)
        prj_name_str, src_list_str, src_data_str = format_BoT_data(prj_name, src_list, src_data)
        write_BoT_data(prj_name_str, src_list_str, src_data_str)
    else:
      print("Please specify a file name")


