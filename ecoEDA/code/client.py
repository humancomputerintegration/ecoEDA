"""Client server to run in background while working in KiCad
"""
import argparse
import time
import os, sys

import json

from pythonosc import udp_client
from ecoEDA_suggestions import ecoEDA_Suggester

from schematic_rw import UpdatedSchematicParser

"""
Initialize what schematic file to look at -- ip/ports should not change, can take out
"""
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="127.0.0.1",
      help="The ip of the OSC server")
    parser.add_argument("--port", type=int, default=5005,
      help="The port the OSC server is listening on")
    parser.add_argument("--file", default="",
      help="The kicad schematic file to watch for")
    parser.add_argument("--resetdict", action='store_true',
      help="delete existing schematic dict - resets project status ")
    args = parser.parse_args()
    client = udp_client.SimpleUDPClient(args.ip, args.port)
    reset_dict = args.resetdict

    if(args.file != ""):
        myfile = args.file

        sch_parser = UpdatedSchematicParser(myfile, reset_dict)

        """
        if new saved file has an updated time, parse through for new components
        note: (1) this changes with autosave behavior
        """

        changes = {myfile:os.path.getmtime(myfile)}
        while True:
            if changes.get(myfile) < os.path.getmtime(myfile):
              sch_parser.update_dict()
              added_cmpn = sch_parser.get_new_component()
              if added_cmpn is not None:
                  suggester = ecoEDA_Suggester(added_cmpn)

                  match_type, match_cmpn, match_dict = suggester.find_match_type()
                  if match_type == "exact match":
                      match_dict["lib_id"] = "ecoEDA:" + match_cmpn
                      client.send_message("/orig_part", json.dumps(added_cmpn))
                      client.send_message("/exact_match", json.dumps(match_dict))
                  elif match_type == "drop-in":
                      match_dict["lib_id"] = "ecoEDA:" + match_cmpn
                      client.send_message("/orig_part", json.dumps(added_cmpn))
                      client.send_message("/drop_in", json.dumps(match_dict))
                  elif match_type == "diff fp":
                      match_dict["lib_id"] = "ecoEDA:" + match_cmpn
                      client.send_message("/orig_part", json.dumps(added_cmpn))
                      client.send_message("/diff_fp", json.dumps(match_dict))
                  elif match_type == "rank":
                      sugg_list = suggester.get_suggestions()
                      client.send_message("/orig_part", json.dumps(added_cmpn))
                      client.send_message("/ranked_list", json.dumps(sugg_list))
                  elif match_type == "subcircuit":
                      match_dict["lib_id"] = "ecoEDA:" + match_cmpn
                      client.send_message("/orig_part", json.dumps(added_cmpn))
                      client.send_message("/subcircuit", json.dumps(match_dict))
                  changes[myfile] = os.path.getmtime(myfile)

              time.sleep(1)
