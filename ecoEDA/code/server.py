import os, sys
UTIL_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), 'util'))
sys.path.append(UTIL_DIR)

from pythonosc import dispatcher, udp_client
from pythonosc import osc_server
import threading
import sexpr
import argparse

from Objectifier import Objectifier

from schematic_rw import ComponentReplacer

from ecoEDA_suggestions import ecoEDA_Suggester

from ecoEDA_data_utils import set_component_reviewed, load_ecoEDA_data, update_project, reset_dismissed, log_data

from sexpdata import dumps

import json
import time

class Replacement_Helper():
    def __init__(self):
        self.new_replacement = ""
        self.old_replacement = ""
    def new_part(self, new_replacement):
        self.new_replacement = new_replacement
    def old_part(self, old_replacement):
        self.old_replacement = old_replacement
    def set_sch_file(self, file):
        self.myfile = file


def n_cmpn(unused_addr, args):
    helper.new_part(args)

def o_cmpn(unused_addr, args):
    helper.old_part(args)

def signal(unused_addr,args):
    """
    Signal to run rewriting of schematic file

    Input arguments:
        args - component uuid
    """
    f_name = open(helper.myfile)
    lines = '\n'.join(f_name.readlines())
    sexpr_data = sexpr.parse_sexp(lines)
    replacer = ComponentReplacer(helper.new_replacement, helper.old_replacement, args, sexpr_data, helper.myfile)
    replacer.run()

    log_data("NEW_REPLACEMENT: " + helper.new_replacement + ", OLD COMPONENT: " + helper.old_replacement + ", FILE: " + helper.myfile)

    time.sleep(1)
    client = udp_client.SimpleUDPClient("127.0.0.1", 5005)
    client.send_message("/unlock", "test")

def update_data(unused_addr, args):
    data = load_ecoEDA_data()
    sch = Objectifier(helper.myfile)
    root = sch.root
    prj_uuid = dumps(root.xpath('/kicad_sch/uuid')[0].childs[0])
    set_component_reviewed(data, prj_uuid, args)

def update_settings(unused_addr, args):
    update_filters(json.loads(args))

def subcircuit_run(unused_addr, args):
    # write to file
    f_name = open(helper.myfile)
    lines = '\n'.join(f_name.readlines())
    sexpr_data = sexpr.parse_sexp(lines)
    replacer = ComponentReplacer(helper.new_replacement, helper.old_replacement, args, sexpr_data, helper.myfile)
    replacer.subcircuit_run()


    #update ecoEDA_data.json
    data = load_ecoEDA_data()
    sch = Objectifier(helper.myfile)
    root = sch.root
    prj_uuid = dumps(root.xpath('/kicad_sch/uuid')[0].childs[0])

    update_project(helper.myfile, data, False, prj_uuid)
    sc_name = helper.new_replacement.split("Subcircuit-")[1]
    f_name = open("./subcircuits/"+sc_name+".kicad_sch")
    lines = '\n'.join(f_name.readlines())
    sc_data = sexpr.parse_sexp(lines)

    sc_sym_uuids = []
    for element in sc_data:
        if type(element) == type([]):
            if (element[0] == 'symbol_instances'):
                sc_sym_instances = element[1:]
                for sym_instance in sc_sym_instances:
                    sc_sym_uuids.append(sym_instance[1][1:])

    for sym_uuid in sc_sym_uuids:
        set_component_reviewed(data, prj_uuid, sym_uuid)


    log_data("SUBCIRCUIT REPLACEMENT: " + helper.new_replacement + ", OLD COMPONENT: " + helper.old_replacement + ", FILE: " + helper.myfile)

    time.sleep(2)
    client = udp_client.SimpleUDPClient("127.0.0.1", 5005)
    client.send_message("/unlock", "unlock")

def dismiss_suggestion(unused_addr, args):
    data = load_ecoEDA_data()
    sch = Objectifier(helper.myfile)
    root = sch.root
    prj_uuid = dumps(root.xpath('/kicad_sch/uuid')[0].childs[0])
    set_component_reviewed(data, prj_uuid, args, False)

    log_data("DISMISSED COMPONENT: " + helper.new_replacement + ", OLD COMPONENT: " + helper.old_replacement + ", FILE: " + helper.myfile)


def revisit_dismissed(unused_addr, args):
    data = load_ecoEDA_data()
    sch = Objectifier(helper.myfile)
    root = sch.root
    prj_uuid = dumps(root.xpath('/kicad_sch/uuid')[0].childs[0])

    reset_dismissed(data, prj_uuid)
    log_data("REVISED DISMISSED PRESSED")

def see_ranked(unused_addr, args):
    #get ranked suggestions for this component
    #send client message to pyshell server
    suggester = ecoEDA_Suggester(json.loads(args))
    sugg_list = suggester.get_suggestions()

    client = udp_client.SimpleUDPClient("127.0.0.1", 5005)
    client.send_message("/orig_part", args)
    client.send_message("/ranked_list", json.dumps(sugg_list))
    log_data("SEE RANKED SELECTED FOR: " + json.loads(args)["lib_id"])

def kicad_log(unused_addr, args):
    log_data("[KICAD UI]" + args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="127.0.0.1",
      help="The ip of the OSC server")
    parser.add_argument("--port", type=int, default=5006,
      help="The port the OSC server is listening on")
    parser.add_argument("--file", default="",
      help="The kicad schematic file to watch for")
    args = parser.parse_args()

    helper = Replacement_Helper()
    dispatcher = dispatcher.Dispatcher()
    dispatcher.map("/run", signal)
    dispatcher.map("/n_cmpn", n_cmpn)
    dispatcher.map("/o_cmpn", o_cmpn)
    dispatcher.map("/update_dict", update_data)
    dispatcher.map("/settings", update_settings)
    dispatcher.map("/subcircuit_run", subcircuit_run)
    dispatcher.map("/dismiss_suggestion", dismiss_suggestion)
    dispatcher.map("/revisit_dismissed", revisit_dismissed)
    dispatcher.map("/see_ranked", see_ranked)
    dispatcher.map("/kicad_log", kicad_log)

    if(args.file != ""):
      helper.set_sch_file(args.file)

    server = osc_server.ThreadingOSCUDPServer((args.ip, args.port), dispatcher)
    print("Serving on {}".format(server.server_address))
    server.serve_forever()
