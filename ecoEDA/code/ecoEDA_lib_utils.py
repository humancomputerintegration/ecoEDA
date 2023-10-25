"""
Organizes ecoEDA symbol library into an easily parseable format
"""
import os, sys

UTIL_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), 'util'))
sys.path.append(UTIL_DIR)

import sexpr
import json

def _get_array(data, value, result=None, level=0, max_level=None):
    """return the array which has value as first element"""
    if result is None: result = []

    if max_level is not None and max_level <= level:
        return result

    level += 1

    for i in data:
        if type(i) == type([]):
            _get_array(i, value, result, level=level, max_level=max_level)
        else:
            if i == value:
                result.append(data)
    return result

def convert_vals(val):
    new_value = int((val*5)) + 250
    return new_value

def convert_y_vals(val):
    new_value = int((val*-5)) + 250
    return new_value

def multiply_vals(val):
    return int(val*5)

#adapted from https://www.geeksforgeeks.org/equation-of-circle-when-three-points-on-the-circle-are-given/
def get_center(x1,y1,x2,y2,x3,y3):
    x12 = x1 - x2;
    x13 = x1 - x3;

    y12 = y1 - y2;
    y13 = y1 - y3;

    y31 = y3 - y1;
    y21 = y2 - y1;

    x31 = x3 - x1;
    x21 = x2 - x1;

    # x1^2 - x3^2
    sx13 = pow(x1, 2) - pow(x3, 2);

    # y1^2 - y3^2
    sy13 = pow(y1, 2) - pow(y3, 2);

    sx21 = pow(x2, 2) - pow(x1, 2);
    sy21 = pow(y2, 2) - pow(y1, 2);

    f = (((sx13) * (x12) + (sy13) *
          (x12) + (sx21) * (x13) +
          (sy21) * (x13)) // (2 *
          ((y31) * (x12) - (y21) * (x13))));

    g = (((sx13) * (y12) + (sy13) * (y12) +
          (sx21) * (y13) + (sy21) * (y13)) //
          (2 * ((x31) * (y12) - (x21) * (y13))));


    # eqn of circle be x^2 + y^2 + 2*g*x + 2*f*y + c = 0
    # where centre is (h = -g, k = -f) and
    # radius r as r^2 = h^2 + k^2 - c
    cx = -g;
    cy = -f;

    return cx,cy


def get_order(element):
    if list(element)[0] == 'rectangle':
        return 0
    elif list(element)[0] == 'pline':
        return 1
    else:
        return 2

def get_ecoEDA_library(library_file):
    """
    returns a library object that is easily parseable - contins the names
    keywords and description of library symbols

    Returns:
        library - dict with symbols and their corresponding keywords, descriptions
    """
    library = dict()

    f_name = open(library_file)
    lines = ''.join(f_name.readlines())
    sexpr_data = sexpr.parse_sexp(lines)
    sym_list = _get_array(sexpr_data, 'symbol', max_level=2)
    f_name.close()

    for item in sym_list:
        if item.pop(0) != 'symbol':
            raise ValueError('unexpected token in file')
        partname = item.pop(0).split(':')[-1]
        library[partname]=dict()

        for prop in _get_array(item, 'property'):
            if(prop[1] == 'Value'):
                if(prop[2].find('\n') == -1):
                    library[partname]['Value']= prop[2]
            if(prop[1] == 'SMD vs. THT'):
                if(prop[2].find('\n') == -1):
                    library[partname]['SMD vs. THT']= prop[2]
            if(prop[1] == 'Drop-in replacement'):
                if(prop[2].find('\n') == -1):
                    library[partname]['Drop-in replacement']= prop[2]
            if(prop[1] == 'Exact match'):
                if(prop[2].find('\n') == -1):
                    library[partname]['Exact match']= prop[2]
            if(prop[1] == 'Species'):
                if(prop[2].find('\n') == -1):
                    library[partname]['Species']= prop[2]
            if(prop[1] == 'Genus'):
                if(prop[2].find('\n') == -1):
                    library[partname]['Genus']= prop[2]
            if(prop[1] == 'Footprint'):
                if(prop[2].find('\n') == -1):
                    library[partname]['Footprint']= prop[2]
            if(prop[1] == 'Quantity'):
                if(prop[2].find('\n') == -1):
                    library[partname]['Quantity']= prop[2]
            if(prop[1] == 'Source'):
                if(prop[2].find('\n') == -1):
                    library[partname]['Source']= prop[2]
            if(prop[1] == 'ki_keywords'):
                if(prop[2].find('\n') == -1):
                    library[partname]['ki_keywords']= prop[2]
            if(prop[1] == 'ki_description'):
                if(prop[2].find('\n') == -1):
                    desc = prop[2].strip('\n')
                    library[partname]['ki_description']= desc

    return library

def get_sym_elements_for_component(library_file, cmpn_name):
    '''Parse through ecoEDA library to find the components symbol elements for drawing

    Returns Symbol Elements and Symbol Bounds for drawing
    '''
    f_name = open(library_file, encoding='utf-8') #hard coded element that should be passed
    lines = ''.join(f_name.readlines())
    sexpr_data = sexpr.parse_sexp(lines)
    sym_list = _get_array(sexpr_data, 'symbol', max_level=2)
    f_name.close()

    sym_draw_elements = []
    bounds = {}

    for item in sym_list:
        if item.pop(0) != 'symbol':
            raise ValueError('unexpected token in file')
        partname = item.pop(0)
        if partname == cmpn_name:
            pin_name_hide = False
            pin_num_hide = False
            pin_num_offset = 1
            pin_name_offset = 1
            min_x = 50
            max_x = -50
            min_y = 50
            max_y = -50

            for result in _get_array(item, 'pin_numbers'):
                for val in result:
                    if type(val) == type([]):
                        pin_num_offset = val[1]
                    elif val == 'hide':
                        pin_num_hide = True

            for result in _get_array(item, 'pin_names'):
                for val in result:
                    if type(val) == type([]):
                        pin_name_offset = val[1]
                    elif val == 'hide':
                        pin_name_hide = True

            sym_draw_elements = list()
            for sym_element in _get_array(item, 'symbol'):
                for element in sym_element:
                    if(element[0] == 'arc'):
                        start = element[1][1:]
                        end = element[3][1:]
                        min_x = min(min_x, start[0], end[0])
                        min_y = min(min_y, start[1], end[1])
                        max_x = max(max_x, start[0], end[0])
                        max_y = max(max_y, start[1], end[1])
                        arc_data_obj = {'arc':{'sx': element[1][1],
                                                'sy': element[1][2],
                                                'mx': element[2][1],
                                                'my': element[2][2],
                                                'ex': element[3][1],
                                                'ey': element[3][2]}}
                        sym_draw_elements.append(arc_data_obj)
                    if(element[0] == 'circle'):
                        center = [element[1][1], element[1][2]]
                        radius = element[2][1]
                        circle_data_obj = {'circle': {'cx': element[1][1],
                                                        'cy': element[1][2],
                                                        'r': element[2][1]}}
                        sym_draw_elements.append(circle_data_obj)
                        min_x = min(min_x, center[0] - radius)
                        min_y = min(min_y, center[1] - radius)
                        max_x = max(max_x, center[0] + radius)
                        max_y = max(max_y, center[1] + radius)
                    if(element[0] == 'rectangle'):
                         rect_data_obj = {'rectangle': {'sx': element[1][1],
                                                        'sy': element[1][2],
                                                        'ex': element[2][1],
                                                        'ey': element[2][2],
                                                        'fill': element[4][1][1]}}

                         sym_draw_elements.append(rect_data_obj)
                         min_x = min(min_x, element[1][1],element[2][1])
                         min_y = min(min_y,element[1][2], element[2][2])
                         max_x = max(max_x, element[1][1], element[2][1])
                         max_y = max(max_y, element[1][2], element[2][2])
                    if(element[0] == 'pin'):
                        pin_data_obj = {'pin': {'x': element[3][1],
                                                'y': element[3][2],
                                                'o': element[3][3],
                                                'l': element[4][1],
                                                'name': element[5][1],
                                                'number': element[6][1],
                                                'hide_name': pin_name_hide,
                                                'hide_num': pin_num_hide,
                                                'name_offset': pin_name_offset,
                                                'num_offset': pin_num_offset}}
                        sym_draw_elements.append(pin_data_obj)
                        min_x = min(min_x, element[3][1])
                        min_y = min(min_y, element[3][2])
                        max_x = max(max_x, element[3][1])
                        max_y = max(max_y, element[3][2])
                    if (element[0] == 'polyline'):
                        pts = []
                        for point in element[1][1:]:
                            pts.append([point[1], point[2]])
                            min_x = min(min_x, point[1])
                            min_y = min(min_y, point[2])
                            max_x = max(max_x, point[1])
                            max_y = max(max_y, point[2])
                        pline_data_obj = {'pline': pts}
                        sym_draw_elements.append(pline_data_obj)
            sym_draw_elements.sort(key=get_order)
            bounds = {'min_x': min_x, 'min_y': min_y, 'max_x': max_x, 'max_y': max_y}
    return sym_draw_elements, bounds


def eco_parse(library_file, n_cmpn):
    """Parse through ecoEDA library to find matching component for replacing.

    Returns:
        new_comp - name of new component
        func - reference symbol object (in header of schematic file)
        prop_array - array of property fields
    """

    f_name = open(library_file)
    lines = ''.join(f_name.readlines())
    eco_sexpr_data = sexpr.parse_sexp(lines)
    eco_sym_list = _get_array(eco_sexpr_data, 'symbol', max_level=2)

    sym_name = n_cmpn
    if(sym_name[0:7] == 'ecoEDA:'):
        sym_name = n_cmpn[7:]

    #default return values
    new_comp = ''
    func = ''
    new_val = ''
    new_sheet = ''
    new_ref = ''
    new_src = ''
    new_eco = ''
    new_fprint = ''
    new_numpins = 0
    new_pins = []

    prop_array = []

    # parse through all items in the ecoEDA symbol library to find the one
    # that matches the selected new component
    for eco_item in eco_sym_list:

        #if names of components match
        if eco_item[1] == sym_name:
            func = eco_item
            func[1] = 'ecoEDA:' + func[1]
            new_comp = eco_item[1]
            # parse through properties and assign values
            for prop in _get_array(eco_item, 'property'):
                prop_array.append(prop)
            for pin in _get_array(eco_item, 'pin'):
                new_numpins = new_numpins + 1
                for pin_head in _get_array(pin, 'number'):
                    new_pins.append(pin_head[1])
    return new_comp, func, prop_array, new_numpins, new_pins

def get_parsed_library(library_file):
    f_name = open(library_file)
    lines = ''.join(f_name.readlines())
    eco_sexpr_data = sexpr.parse_sexp(lines)

    return eco_sexpr_data

def get_num_lib_cmpnts(library_file):
    f_name = open(library_file)
    lines = ''.join(f_name.readlines())
    eco_sexpr_data = sexpr.parse_sexp(lines)
    count = 0
    for element in eco_sexpr_data:
        if type(element) == type([]):
            if element[0] == 'symbol':
                count +=1
    return count
