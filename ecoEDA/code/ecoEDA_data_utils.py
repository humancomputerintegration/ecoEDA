import os, sys

UTIL_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), 'util'))
sys.path.append(UTIL_DIR)

from Objectifier import Objectifier
from sexpdata import dumps
import json
import time

def check_filter(data, proj_id, filter_type, filter_flag):
    """
    goes through ecoEDA_data.json to check if filter is on or not.

    Input Arguments:
        data: dict of ecoEDA data to parse through
        proj_id: project id to check in, or 'global' if looking through global settings
        filter_type: i.e. Footprint, Component Type, etc.
        filter_flag: i.e. SMD, DIP, Microcontrollers, Capacitors

    Returns:
        true or false
    """

    if proj_id == 'global':
        return data["global settings"]["filters"][filter_type][filter_flag]
    else:
        if proj_id in data["projects"].keys():
            return data["projects"][proj_id]["filters"][filter_type][filter_flag]

def add_new_project(myfile, data):
    """
    adds new project and relevant identifiers to ecoEDA data

    Input Arguments:
        myfile: the project file that needs to be added
        data: ecoEDA tool data
    Returns:
        data: updated ecoEDA tool data
    """
    schema = Objectifier(myfile)
    root = schema.root
    prj_uuid = dumps(root.xpath('/kicad_sch/uuid')[0].childs[0])

    proj_dir = os.path.dirname(myfile)
    proj_name = os.path.basename(myfile)

    prj_dict = dict({"proj_name": proj_name, "proj_dir": proj_dir, "components": {}})
    components = prj_dict["components"]
    for node in root.xpath('/kicad_sch/symbol'):
        symbol = node.xpath('lib_id')[0].childs[0]
        s_uuid = dumps(node.xpath('uuid')[0].childs[0])

        components[s_uuid] = dict()
        components[s_uuid]['lib_id'] = symbol
        for _ in node.xpath('property'):
            if(_.childs[:2][0] == 'Value'):
                components[s_uuid]['Value'] = _.childs[:2][1]
                components[s_uuid]['reviewed'] = False
            if(_.childs[:2][0] == 'ki_keywords'):
                components[s_uuid]['ki_keywords'] = _.childs[:2][1]
            if(_.childs[:2][0] == 'ki_description'):
                components[s_uuid]['ki_description'] = _.childs[:2][1]

    data["projects"][prj_uuid] = prj_dict

    with open('ecoEDA_data.json', 'w') as f:
        json.dump(data, f)

    return data

def update_project(myfile, data, reset_dict, proj_id):
    """
    updates a ecoEDA_data.json file that stores components in the schematic
    file and if suggestions have been reviewed or not

    also handles for the case when symbols get deleted
    Input Arguments:
        reset_dict - flag (bool) for if the schema_dict.json file needs to be reset
    """
    f_name = open(myfile)
    lines = '\n'.join(f_name.readlines())
    while len(lines) == 0:
        time.sleep(1)
        f_name = open(myfile)
        lines = '\n'.join(f_name.readlines())
    sch = Objectifier(myfile)
    root = sch.root

    #if ecoEDA_data.json exists, load it, otherwise create anew
    
    if "projects" not in data.keys():
        data["projects"] = {}

    if proj_id in data["projects"].keys():
        if reset_dict:
            data["projects"].pop(proj_id)
            add_new_project(myfile, data)
        else:
            sch_uuid_list = []
            cmpnts_data = data["projects"][proj_id]["components"]
            sym_list = cmpnts_data.keys()

            for node in root.xpath('/kicad_sch/symbol'):
                symbol = node.xpath('lib_id')[0].childs[0]
                s_uuid = dumps(node.xpath('uuid')[0].childs[0])
                sch_uuid_list.append(s_uuid)
                if s_uuid not in sym_list: #if symbol uuid is not in the list, add it
                    cmpnts_data[s_uuid] = dict()
                    cmpnts_data[s_uuid]['lib_id'] = symbol
                    cmpnts_data[s_uuid]['reviewed'] = False
                    for _ in node.xpath('property'):
                        if(_.childs[:2][0] == 'Value'):
                            cmpnts_data[s_uuid]['Value'] = _.childs[:2][1]
                        if(_.childs[:2][0] == 'ki_keywords'):
                            cmpnts_data[s_uuid]['ki_keywords'] = _.childs[:2][1]
                        if(_.childs[:2][0] == 'ki_description'):
                            cmpnts_data[s_uuid]['ki_description'] = _.childs[:2][1]
                        if(_.childs[:2][0] == 'ecoEDA'): # handles for when an ecoEDA symbol
                            log_data("ecoEDA COMPONENT ADDED MANUALLY: " + symbol)
                            cmpnts_data[s_uuid]['reviewed'] = True
            # handles for if an old component was deleted in the schematic
            if(len(cmpnts_data.keys()) != len(sch_uuid_list)):
                for key in list(cmpnts_data.keys()):
                    if key not in sch_uuid_list:
                        cmpnts_data.pop(key, None)

        with open('ecoEDA_data.json', 'w') as f:
            json.dump(data, f)
    else:
        data = add_new_project(myfile, data)

    return data

def load_ecoEDA_data():
    with open('ecoEDA_data.json', 'r+') as f:
        try:
            ecoEDA_data = json.load(f)
        except:
            ecoEDA_data = {}
            json.dump(ecoEDA_data, f)
    return ecoEDA_data

def set_component_reviewed(data, proj_id, comp_uuid, is_ecoEDA=True):
    if proj_id in data["projects"].keys():
            cmpnts_data = data["projects"][proj_id]["components"]
            if comp_uuid in cmpnts_data.keys():
                cmpnts_data[comp_uuid]["reviewed"] = True
                if not is_ecoEDA:
                    cmpnts_data[comp_uuid]["not replaced"] = True
                else:
                    if "not replaced" in cmpnts_data[comp_uuid].keys():
                        cmpnts_data[comp_uuid]["not replaced"] = False
                with open('ecoEDA_data.json', 'w') as f:
                    json.dump(data, f)

def reset_dismissed(data, proj_id):
    if proj_id in data["projects"].keys():
        cmpnts_data = data["projects"][proj_id]["components"]
        for comp in cmpnts_data:
            if "not replaced" in cmpnts_data[comp].keys():
                if cmpnts_data[comp]["not replaced"]:
                    cmpnts_data[comp]["reviewed"] = False

    with open('ecoEDA_data.json', 'w') as f:
        json.dump(data, f)

def get_project_files_list(data):
    prj_list = []
    for proj in data["projects"]:
        prj_file = data["projects"][proj]['proj_dir'] + "/" + data["projects"][proj]['proj_name']
        if os.path.exists(prj_file):
            prj_list.append(prj_file)
    return prj_list

'''
def update_filters(n_filters):
    data = load_ecoEDA_data()
    data["global settings"]["filters"] = n_filters
    with open('ecoEDA_data.json', 'w') as f:
        json.dump(data, f)

def load_filters():
    data = load_ecoEDA_data()
    filters = data["global settings"]["filters"]

    abr_filters = dict()
    for filter_type in filters:
        for id in filters[filter_type]:
            if not filters[filter_type][id]:
                abr_filters[filter_type] = id
    return abr_filters
'''


def log_data(text):
    ''' only used for study purposes to log ecoEDA use; for public repo, logging data was removed.
    '''
    t = time.localtime()
    current_time = time.ctime()

    f = open("data_log.txt", "a")
    f.write(current_time + " ---- ")
    f.write(text)
    f.write("\n")
    f.close()
