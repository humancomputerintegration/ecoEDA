import os, sys

UTIL_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), 'util'))
sys.path.append(UTIL_DIR)

import sexpr

import uuid
from common import sexp_indent

from ecoEDA_lib_utils import eco_parse
from ecoEDA_data_utils import update_project, load_ecoEDA_data
from Objectifier import Objectifier,Node

from sexpdata import dumps
import json
import os.path

import time

def get_order(element):
    if list(element)[0] == 'rectangle':
        return 0
    elif list(element)[0] == 'pline':
        return 1
    else:
        return 2

def compile_draw_data(node, pin_flags, bounds, offset_x = 0, offset_y = 0):
    sym_draw_elements = []
    min_x = bounds['min_x']
    max_x = bounds['max_x']
    min_y = bounds['min_y']
    max_y = bounds['max_y']

    for a_ in node.xpath('arc'):
        start = a_.xpath('start')[0]._childs
        mid = a_.xpath('mid')[0]._childs
        end = a_.xpath('end')[0]._childs
        s_x = start[0] + offset_x
        s_y = start[1] + offset_y
        m_x = mid[0] + offset_x
        m_y = mid[1] + offset_y
        e_x = end[0] + offset_x
        e_y = end[1] + offset_y
        min_x = min(min_x, s_x, e_x)
        min_y = min(min_y, s_y, e_y)
        max_x = max(max_x, s_x, e_x)
        max_y = max(max_y, s_y, e_y)
        arc_data_obj = {'arc':{'sx': s_x,
                                'sy': s_y,
                                'mx': m_x,
                                'my': m_y,
                                'ex': e_x,
                                'ey': e_y}}
        sym_draw_elements.append(arc_data_obj)
    for c_ in node.xpath('circle'):
        center = c_.xpath('center')[0]._childs
        radius = c_.xpath('radius')[0].first_child
        c_x = center[0] + offset_x
        c_y = center[1] + offset_y
        circle_data_obj = {'circle': {'cx': c_x,
                                       'cy': c_y,
                                       'r': radius}}
        sym_draw_elements.append(circle_data_obj)
        min_x = min(min_x, center[0] - radius)
        min_y = min(min_y, center[1] - radius)
        max_x = max(max_x, center[0] + radius)
        max_y = max(max_y, center[1] + radius)
    for r_ in node.xpath('rectangle'):
        start = r_.xpath('start')[0]._childs
        end = r_.xpath('end')[0]._childs
        s_x = start[0] + offset_x
        s_y = start[1] + offset_y
        e_x = end[0] + offset_x
        e_y = end[1] + offset_y
        fill = dumps(r_.xpath('fill/type')[0].first_child)
        rect_data_obj = {'rectangle': {'sx': s_x,
                                       'sy': s_y,
                                       'ex': e_x,
                                       'ey': e_y,
                                       'fill': fill}}
        sym_draw_elements.append(rect_data_obj)
        min_x = min(min_x, start[0], end[0])
        min_y = min(min_y, start[1], end[1])
        max_x = max(max_x, start[0], end[0])
        max_y = max(max_y, start[1], end[1])
    for p_ in node.xpath('pin'):
        at = p_.xpath('at')[0]._childs
        at_x = at[0] + offset_x
        at_y = at[1] + offset_y
        length = p_.xpath('length')[0].first_child
        name = p_.xpath('name')[0].first_child
        number = p_.xpath('number')[0].first_child
        pin_data_obj = {'pin': {'x': at_x,
                                'y': at_y,
                                'o': at[2],
                                'l': length,
                                'name': name,
                                'number': number,
                                'hide_name': pin_flags['hide_name'],
                                'hide_num': pin_flags['hide_num'],
                                'name_offset': pin_flags['name_offset']}}
        sym_draw_elements.append(pin_data_obj)
        min_x = min(min_x, at[0])
        min_y = min(min_y, at[1])
        max_x = max(max_x, at[0])
        max_y = max(max_y, at[1])
    for pl_ in node.xpath('polyline'):
        pts = []
        for point in pl_.xpath('pts/xy'):
            
            pt_x = point._childs[0] + offset_x
            pt_y = point._childs[1] + offset_y
            pts.append([pt_x, pt_y])
            min_x = min(min_x, pt_x)
            min_y = min(min_y, pt_y)
            max_x = max(max_x, pt_x)
            max_y = max(max_y, pt_y)
        pline_data_obj = {'pline': pts}
        sym_draw_elements.append(pline_data_obj)

    bounds = {'min_x': min_x, 'min_y': min_y, 'max_x': max_x, 'max_y': max_y}
    return sym_draw_elements, bounds

def get_subcircuit_draw_elements(ecoEDA_dir, subcircuit_name):
    sch = Objectifier(ecoEDA_dir + "subcircuits/"+subcircuit_name+".kicad_sch")
    root = sch.root

    sym_draw_elements = list()
    min_x = 500
    max_x = -500
    min_y = 500
    max_y = -500

    for node in root.xpath('wire/pts'):
        pts = []
        for xy in node.xpath('xy'):
            pts.append([xy.childs[0], xy.childs[1]*-1])
            min_x = min(min_x, xy.childs[0])
            min_y = min(min_y, xy.childs[1]*-1)
            max_x = max(max_x, xy.childs[0])
            max_y = max(max_y, xy.childs[1]*-1)
        pline_data_obj = {'pline': pts}
        sym_draw_elements.append(pline_data_obj)

    for node in root.xpath('label'):
        text = node.first_child
        x = node.xpath('at')[0].childs[0]
        y = node.xpath('at')[0].childs[1] * -1
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)
        label_data_obj = {'label': {'text': text, 'x': x, 'y': y}}
        sym_draw_elements.append(label_data_obj)

    for node in root.xpath('symbol'):
        lib_id = node.first_child.first_child
        x = node.childs[1].childs[0]
        y = node.childs[1].childs[1] * -1

        for ls_node in root.xpath('lib_symbols/symbol'):
            if ls_node.first_child == lib_id:
                hide_name = True
                hide_num = True
                name_offset = 1
                pn_ = ls_node.xpath('pin_names')
                if len(pn_) > 0:
                    hide_name = len(ls_node.xpath('pin_names/hide')) > 0
                    name_offset = pn_[0].xpath('offset')[0].first_child
                hide_num = len(ls_node.xpath('pin_numbers/hide')) > 0
                pin_flags = {'hide_name': hide_name, 'hide_num': hide_num, 'name_offset': name_offset}
                bounds = {'min_x': min_x, 'min_y': min_y, 'max_x': max_x, 'max_y': max_y}

                for ls_s_node in ls_node.xpath('symbol'):
                    s_draw_elements, s_bounds = compile_draw_data(ls_s_node, pin_flags, bounds, x, y)
                    min_x = min(min_x, s_bounds['min_x'])
                    min_y = min(min_y, s_bounds['min_y'])
                    max_x = max(max_x, s_bounds['max_x'])
                    max_y = max(max_y, s_bounds['max_y'])
                    sym_draw_elements.extend(s_draw_elements)



    bounds = {'min_x': min_x, 'min_y': min_y, 'max_x': max_x, 'max_y': max_y}
    return sym_draw_elements, bounds

class ComponentReplacer():
    def __init__(self, n_cmpn, o_cmpn, o_cmpn_uuid, sexpr_data, file):
        self.n_cmpn = n_cmpn
        self.o_cmpn = o_cmpn
        self.n_cmpn_vals = []
        self.o_cmpn_uuid = o_cmpn_uuid
        self.data = sexpr_data
        self.myfile = file
        self.sc_file = ''
        self.sc_data = None
        self.o_cmpn_loc = []

    def _get_array(self, data, value, result=None, level=0, max_level=None):
        """return the array which has value as first element (recursive function)
        Input Arguments:
            data - tree to parse through
            value - value being searched for
            result - default None
            level - tree level
            max_level - max tree level
        Returns:
            result - array
        """
        if result is None: result = []

        if max_level is not None and max_level <= level:
            return result

        level += 1
        for i in data:
            if type(i) == type([]):
                self._get_array(i, value, result, level=level, max_level=max_level)
            else:
                if i == value:
                    result.append(data)
        return result

    def formulate_pins(self):
        """forms an array of arrays of pins and their properties according to
        the number of pins; attaches new uuids to each one

        Returns:
            pin_set - formatted array of pins
        """

        n_cmpn = self.n_cmpn
        eco_cmpn = self.n_cmpn_vals
        pin = []
        pin_set = []
        unique_id = []
        num = eco_cmpn[3]

        b = 0
        for a in range (num):
            pin = []
            pin.append('pin')
            pin.append(eco_cmpn[4][b])
            unique_id = []
            unique_id.append("uuid")
            unique_id.append(str(uuid.uuid4()))
            pin.append(unique_id)
            pin_set.append(pin)
            b = b + 1

        return pin_set

    def get_num_symbol_instances(self):
        """
        get how many symbol instances in the schematic
        """
        count = 0
        for element in self.data:
            if type(element) == type([]):
                if (element[0] == 'symbol'):
                    if element[1][1] == self.o_cmpn:
                        count += 1
        return count

    def append_symbol_library(self):
        """append symbol library to header of schematic file
        """
        new_cmpnt_vals = self.n_cmpn_vals

        for element in self.data:
            if type(element) == type([]):
                if (element[0] == 'lib_symbols'):
                    symlib_list = []
                    for symlib in element: # just to check if library reference already exists
                        if type(symlib) == type([]):
                            symlib_list.append(symlib[1])
                    if(new_cmpnt_vals[0] not in symlib_list):
                        element.append(new_cmpnt_vals[1])
                    break
                else:
                    continue

    def replace_symbol_library(self):
        """replace symbol library in header of schematic file
        """
        new_cmpnt_vals = self.n_cmpn_vals
        for element in self.data:
            if type(element) == type([]):
                if (element[0] == 'lib_symbols'):
                    for symlib in element:
                        if type(symlib) == type([]):
                            if symlib[1] == self.o_cmpn:
                                 element.pop(element.index(symlib))
                                 break
                        else:
                            continue
                    symlib_list = []
                    for symlib in element: # just to check if library reference already exists
                        if type(symlib) == type([]):
                            symlib_list.append(symlib[1])

                    if(new_cmpnt_vals[0] not in symlib_list):
                        element.append(new_cmpnt_vals[1])
                    break
    def remove_symbol_library(self):
        """remove symbol library in header of schematic file
        """
        for element in self.data:
            if type(element) == type([]):
                if (element[0] == 'lib_symbols'):
                    for symlib in element:
                        if type(symlib) == type([]):
                            if symlib[1] == self.o_cmpn:
                                 element.pop(element.index(symlib))
                                 break

    def replace_sch_component(self):
        """
        Rewrites symbol information for specific component based on uuid
        """
        new_cmpnt_vals = self.n_cmpn_vals
        new_pins = self.formulate_pins()

        for element in self.data:
            if type(element) == type([]):
                if element[0] == 'symbol':
                    for property in element:
                        if type(property) == type([]):
                            if property[0] == 'uuid':
                                if property[1] == self.o_cmpn_uuid:
                                    # located the specific symbol we want
                                    element[1][1] = self.n_cmpn
                                    self.o_cmpn_loc = [element[2][1], element[2][2]]
                                    #delete all old properties and pins
                                    for x_property in list(element): #traversing property list again, creating a copy for easy deletion
                                        if type(x_property) == type([]):
                                            if (x_property[0] == 'property') or (x_property[0] == 'pin'):
                                                element.remove(x_property)

                                    for n_property in new_cmpnt_vals[2]:
                                        if len(n_property) > 1:
                                            if n_property[1] == "Reference":
                                                n_property[4][1] = float(self.o_cmpn_loc[0])
                                                n_property[4][2] = float(self.o_cmpn_loc[1]) + 5
                                                element.append(n_property)
                                            elif n_property[1] == "Value":
                                                n_property[4][1] = float(self.o_cmpn_loc[0])
                                                n_property[4][2] = float(self.o_cmpn_loc[1]) + 10
                                                element.append(n_property)
                                            else:
                                                element.append(n_property)
                                        else:
                                            element.append(n_property)

                                    for n_pin in new_pins:
                                        element.append(n_pin)
                                    break
                            else:
                                continue
                        else:
                            continue

    def replace_sym_instances(self):
        """
        Replaces the last part of schematic file (symbol_instances)
        """

        #get information relevant to symbol_instances fields
        #(reference, unit, value, footprint)
        # to do: handle for unit

        new_cmpnt_vals = self.n_cmpn_vals

        prop_array = new_cmpnt_vals[2]

        n_value = ""
        n_ref = ""
        n_fp = ""

        for prop in prop_array:
            if prop[1] == "Reference":
                n_ref = prop[2] + "?"
            if prop[1] == "Value":
                n_value = prop[2]
            if prop[1] == "Footprint":
                n_fp = prop[2]

        for element in self.data:
            if type(element) == type([]):
                if element[0] == 'symbol_instances':
                    for path in element:
                        if type(path) == type([]):
                            if path[1][1:] == self.o_cmpn_uuid:
                                for property in path:
                                    if type(property) == type([]):
                                        if property[0] == 'reference':
                                            property[1] = n_ref
                                        elif property[0] == 'value':
                                            property[1] = n_value
                                        elif property[0] == 'footprint':
                                            property[1] = n_fp

    def incl_quotes(self):
        """formats all data with proper quotations
        """
        for element in self.data:
            if type(element) == type([]):
                if element[0] == 'paper':
                    element[1] = "\"" + element[1] + "\""
                elif element[0] == 'lib_symbols':
                    for symlib in element:
                        if symlib[0] == 'symbol':
                            symlib[1] = "\"" + symlib[1] + "\""
                            for prop in symlib:
                                if type(prop) == type([]):
                                    if prop[0] == 'property':
                                        prop[1] = "\"" + prop[1] + "\""
                                        prop[2] = "\"" + prop[2].replace("\"", '\\"') + "\""
                                    elif prop[0] == 'symbol':
                                        prop[1] = "\"" + prop[1] + "\""
                                        for text in prop:
                                            if text[0] == 'text':
                                                text[1] == prop[1] == "\"" + text[1] + "\""
                                            elif text[0] == 'pin':
                                                for pin_text in text:
                                                    if (pin_text[0] == 'name') or (pin_text[0] =='number'):
                                                        pin_text[1] = "\"" + pin_text[1] + "\""
                elif element[0] == 'symbol':
                    for property in element:
                        if type(property) == type([]):
                            if property[0] == 'lib_id':
                                property[1] = "\"" + property[1] + "\""
                            elif property[0] == 'property':
                                if(property[1][0] != '"'):
                                    property[1] = "\"" + property[1] + "\""
                                    property[2] = "\"" + property[2] + "\""
                            elif property[0] == 'pin':
                                property[1] = "\"" + property[1] + "\""
                            elif property[0] == 'default_instance':
                                property[1][1] = "\"" + property[1][1] + "\""
                                property[3][1] = "\"" + property[3][1] + "\""
                                property[4][1] = "\"" + property[4][1] + "\""
                elif element[0] == 'sheet_instances':
                    for path in element:
                        if type(path) == type([]):
                            if path[0] == 'path':
                                path[1] = "\"" + path[1] + "\""
                                path[2][1] = "\"" + path[2][1] + "\""
                elif element[0] == 'symbol_instances':
                    for path in element:
                        if path[0] == 'path':
                            for value in path:
                                if (value[0] == 'value') or (value[0] == 'footprint') or (value[0] == 'reference'):
                                    value[1] = "\"" + value[1] + "\""

    def produce(self):
        """writes to schematic file
        Returns:
            indented - nicely formatted string of file
        """
        sexpr_built = sexpr.build_sexp(self.data)
        formatted = sexpr.format_sexp(sexpr_built)#gives it proper bracketting
        indented = sexp_indent(sexpr_built)
        original_stdout = sys.stdout
        with open(self.myfile, 'w') as f: #hardcoded
            sys.stdout = f # Change the standard output to the file we created.
            print(indented)
            sys.stdout = original_stdout
        return indented

    def sc_add_symbol_libraries(self):
        sc_lib_symbols = []
        for element in self.sc_data:
            if type(element) == type([]):
                if (element[0] == 'lib_symbols'):
                    sc_lib_symbols = element[1:]

        for element in self.data:
            if type(element) == type([]):
                if (element[0] == 'lib_symbols'):
                    for lib_symbol in sc_lib_symbols:
                        element.append(lib_symbol)

    def reloc_wire(self, wire_obj):
        pts_arr = wire_obj[1][1:]
        for xy_pt in pts_arr:
            xy_pt[1] = float(xy_pt[1]) + float(self.o_cmpn_loc[0])
            xy_pt[2] = float(xy_pt[2]) + float(self.o_cmpn_loc[1])

        return wire_obj

    def reloc_symbol(self, sym_obj):
        for element in sym_obj:
            if type(element) == type([]):
                if element[0] == 'property':
                    if element[1] == 'Reference':
                        element[4][1] = float(element[4][1]) + float(self.o_cmpn_loc[0])
                        element[4][2] = float(element[4][2]) + float(self.o_cmpn_loc[1])
                    elif element[1] == 'Value':
                        element[4][1] = float(element[4][1]) + float(self.o_cmpn_loc[0])
                        element[4][2] = float(element[4][2]) + float(self.o_cmpn_loc[1])
        return sym_obj

    def sc_add_conn_sym(self):
        for element in self.sc_data:
            if type(element) == type([]):
                if (element[0] == 'junction'):
                    element[1][1] = float(element[1][1]) + float(self.o_cmpn_loc[0])
                    element[1][2] = float(element[1][2]) + float(self.o_cmpn_loc[1])
                    self.data.append(element)
                if (element[0] == 'wire'):
                    reloc_wire_elem = self.reloc_wire(element)
                    self.data.append(reloc_wire_elem)
                if (element[0] == 'label'):
                    element[2][1] = float(element[2][1]) + float(self.o_cmpn_loc[0])
                    element[2][2] = float(element[2][2]) + float(self.o_cmpn_loc[1])
                    self.data.append(element)
                if (element[0] == 'symbol'):
                    element[2][1] = float(element[2][1]) + float(self.o_cmpn_loc[0])
                    element[2][2] = float(element[2][2]) + float(self.o_cmpn_loc[1])
                    reloc_symbol = self.reloc_symbol(element)
                    self.data.append(reloc_symbol)

    def sc_add_sym_instances(self):
        sc_sym_instances = []
        for element in self.sc_data:
            if type(element) == type([]):
                if (element[0] == 'symbol_instances'):
                    sc_sym_instances = element[1:]

        for element in self.data:
            if type(element) == type([]):
                if (element[0] == 'symbol_instances'):
                    for path in sc_sym_instances:
                        element.append(path)

    def sc_remove_symbol(self):
        for element in list(self.data):
            if type(element) == type([]):
                if element[0] == 'symbol':
                    for property in list(element):
                        if type(property) == type([]):
                            if property[0] == 'uuid':
                                if property[1] == self.o_cmpn_uuid:
                                    # located the specific symbol we want
                                    self.o_cmpn_loc = [element[2][1], element[2][2]]
                                    self.data.remove(element)

    def subcircuit_run(self):
        sc_name = self.n_cmpn.split("Subcircuit-")[1]
        f_name = open("./subcircuits/"+sc_name+".kicad_sch")
        lines = '\n'.join(f_name.readlines())
        sexpr_data = sexpr.parse_sexp(lines)

        self.sc_data = sexpr_data

        num_inst = self.get_num_symbol_instances()
        if num_inst == 1:
            self.remove_symbol_library()

        self.sc_remove_symbol()
        self.sc_add_symbol_libraries()
        self.sc_add_conn_sym()
        self.sc_add_sym_instances()
        self.incl_quotes()
        self.produce()


    def run(self):

        self.n_cmpn_vals = eco_parse("./ecoEDA.kicad_sym", self.n_cmpn)
        num_inst = self.get_num_symbol_instances()
        if(num_inst > 1): #as in you shouldn't completely rewrite this structure
            self.append_symbol_library()
        else:
            self.replace_symbol_library()
        self.replace_sch_component()
        self.replace_sym_instances()
        self.incl_quotes()
        self.produce()

class UpdatedSchematicParser():
    """
        Parser to read through file and methods to update dict and get the new component
    """
    def __init__(self, myfile, reset_dict):
        """
        sets the schematic file to read from and determine if dict file needs to be resets
        Input Arguments:
            myfile - schematic file being parsed
            reset_dict - flag (bool) for if the schema_dict.json file needs to be reset
        """
        self.myfile = myfile

        self.sch = Objectifier(myfile)
        root = self.sch.root
        print(root.xpath('/kicad_sch/uuid'))
        if (len(root.xpath('/kicad_sch/uuid')) > 0):
            prj_uuid = dumps(root.xpath('/kicad_sch/uuid')[0].childs[0])
            self.proj_id = prj_uuid
            self.update_dict(reset_dict) #read in schematic to json
        else:
            print("Please add something to your file (i.e., change your schematic title")

    def update_dict (self, reset_dict=False):
        """
        updates a schema_dict.json file that stores components in the schematic
        file and if suggestions have been reviewed or not

        also handles for the case when symbols get deleted
        Input Arguments:
            reset_dict - flag (bool) for if the schema_dict.json file needs to be reset
        """
        ecoEDA_data = load_ecoEDA_data()
        data = update_project(self.myfile, ecoEDA_data, reset_dict, self.proj_id)

        cmpnts_dict = data["projects"][self.proj_id]["components"]

        self.cmpnts_dict = cmpnts_dict #update this regardless of when called
        self.sch = Objectifier(self.myfile)
        return cmpnts_dict

    def get_component_reference(self, cmpnt_uuid):
        root = self.sch.root
        for node in root.xpath('/kicad_sch/symbol_instances/path'):
            if node.first_child == "/" + cmpnt_uuid:
                return node.xpath('reference')[0].first_child

    def get_component_value(self, cmpnt_uuid):
        root = self.sch.root
        for node in root.xpath('/kicad_sch/symbol_instances/path'):
            if node.first_child == "/" + cmpnt_uuid:
                return node.xpath('value')[0].first_child

    def get_new_component(self):
        """
        returns the symbol information for the new component that was added

        Returns (if found):
            cmpnt_uuid - uuid of the new component
            lib_id - symbol name in library
            new_value - value property of lib symbol
            new_keyword - keyword property of library symbol
            new_description - description property of library symbol
        """
        new_value = ""
        new_keyword = ""
        new_description = ""
        new_reference = ""
        new_footprint = ""
        new_draw_elements = list()
        bounds = {'min_x': 50, 'min_y': 50, 'max_x': -50, 'max_y': -50}

        for cmpn_key in self.cmpnts_dict:
            cmpn = self.cmpnts_dict[cmpn_key]
            if not cmpn['reviewed']: # if component has reviewed flag false
                lib_id = cmpn['lib_id']
                if(lib_id.split(":")[0] != 'power'):
                    root = self.sch.root
                    for node in root.xpath('/kicad_sch/lib_symbols/symbol'):
                        #get matching symbol reference
                        if node.first_child == lib_id:
                            hide_name = True
                            hide_num = True
                            name_offset = 1
                            pn_ = node.xpath('pin_names')
                            if len(pn_) > 0:
                                hide_name = (len(pn_[0]) > 1)
                                name_offset = pn_[0].xpath('offset')[0].first_child
                            hide_num = len(node.xpath('pin_numbers/hide')) > 0
                            pin_flags = {'hide_name': hide_name, 'hide_num': hide_num, 'name_offset': name_offset}
                            for s_ in node.xpath('symbol'):
                                data, bounds = compile_draw_data(s_, pin_flags, bounds)
                                new_draw_elements.extend(data)
                            for _ in node.xpath('property'):
                                if(_.childs[:2][0] == 'ki_keywords'):
                                    new_keyword = _.childs[:2][1]
                                if(_.childs[:2][0] == 'ki_description'):
                                    new_description = _.childs[:2][1]
                                if(_.childs[:2][0] == 'Footprint'):
                                    new_footprint = _.childs[:2][1]
                            new_reference = self.get_component_reference(cmpn_key)
                            new_value = self.get_component_value(cmpn_key)
                            new_draw_elements.sort(key=get_order)
                            new_cmpnt_dict = {"uuid": cmpn_key, "lib_id": lib_id, "value": new_value, "ki_keywords": new_keyword, "ki_description": new_description, "reference": new_reference, "Footprint": new_footprint, "Symbol Elements": new_draw_elements, "Symbol Bounds": bounds}
                            return new_cmpnt_dict

