"""
Backend to identify changed component and suggest components to replace it with
"""

import os, sys

import json

import os.path, time
import re

from ecoEDA_lib_utils import get_ecoEDA_library, _get_array
from ecoEDA_data_utils import check_filter


class ecoEDA_Suggester():
    def __init__(self, new_cmpn):
        self.new_component = new_cmpn
        self.eco_lib_dict = get_ecoEDA_library("./ecoEDA.kicad_sym")
        #load project settings/filter information
        self.filters = dict()

    def levenshteinDistance(self, s1, s2):
        """ from https://stackoverflow.com/questions/2460177/edit-distance-in-python """
        if len(s1) > len(s2):
            s1, s2 = s2, s1

        distances = range(len(s1) + 1)
        for i2, c2 in enumerate(s2):
            distances_ = [i2+1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_
        return distances[-1]

    def lcs(self, X, Y):
        #from https://www.geeksforgeeks.org/python-program-for-longest-common-subsequence/
        # find the length of the strings
        m = len(X)
        n = len(Y)

        # declaring the array for storing the dp values
        L = [[None]*(n + 1) for i in range(m + 1)]

        """Following steps build L[m + 1][n + 1] in bottom up fashion
        Note: L[i][j] contains length of LCS of X[0..i-1]
        and Y[0..j-1]"""
        for i in range(m + 1):
            for j in range(n + 1):
                if i == 0 or j == 0 :
                    L[i][j] = 0
                elif X[i-1] == Y[j-1]:
                    L[i][j] = L[i-1][j-1]+1
                else:
                    L[i][j] = max(L[i-1][j], L[i][j-1])

        # L[m][n] contains the length of LCS of X[0..n-1] & Y[0..m-1]
        return L[m][n]

    def get_name_score(self, n_name, lib_component_name):
        edit_dist = self.levenshteinDistance(n_name, lib_component_name)

        lcs = self.lcs(n_name, lib_component_name)
        max_len = max(len(n_name), len(lib_component_name))
        min_len = min(len(n_name), len(lib_component_name))

        return (1 - (edit_dist/max_len)) + (lcs/min_len)

    def get_kw_score(self, n_keyword, lib_component):

        KeyWords = n_keyword.split()

        score = 0
        if "ki_keywords" in lib_component:
            lib_keywords = lib_component["ki_keywords"].lower()
        else:
            lib_keywords = ""

        for word in KeyWords:
            if word in lib_keywords:
                score +=1
        return score

    def get_desc_score(self, n_desc, lib_component):
        Description = n_desc.split()

        score = 0

        if "ki_description" in lib_component:
            lib_desc = lib_component["ki_description"].lower()
        else:
            lib_desc = ""

        for word in Description:
            if word in lib_desc:
                score += 1

        return score

    def get_type_score(self, n_ref, lib_component):
        score = 0
        if n_ref == 'R':
            if lib_component["Species"].lower() == 'resistor':
                score +=2
        elif n_ref == 'C':
            if lib_component["Species"].lower() == 'capacitor':
                score +=2
        elif n_ref == 'D':
            if lib_component["Species"].lower() == 'diode':
                score +=2
        elif n_ref == 'Y':
            if lib_component["Species"].lower() == 'crystal':
                score +=2
        elif n_ref == 'L':
            if lib_component["Species"].lower() == 'inductor':
                score +=2

        return score


    def filter_cmpnt_type(self, cmpn, type):
        return True

    def filter_footprint(self, cmpn, footprint):
        return True

    def passed_filters(self, cmpn_values, cmpn_name):
        return True

    def create_rankings(self):
        n_name = self.new_component["lib_id"].split(":")[1]
        if self.new_component["value"] is not None:
            n_val = self.new_component["value"].lower()
        else:
            n_val = ""
        if self.new_component["ki_keywords"] is not None:
            n_keyword = self.new_component["ki_keywords"].lower()
        else:
            n_keyword = ""
        if self.new_component["ki_description"] is not None:
            n_desc = self.new_component["ki_description"].lower()
        else:
            n_desc = ""
        if self.new_component["reference"] is not None:
            n_ref = self.new_component["reference"].split("?")[0]
        else:
            n_ref = ""

        rankings_dict = dict()

        for cmpn in self.eco_lib_dict:
            if self.passed_filters(self.eco_lib_dict[cmpn], cmpn):
                name_score = self.get_name_score(n_name, cmpn)
                kw_score = self.get_kw_score(n_keyword, self.eco_lib_dict[cmpn])
                desc_score = self.get_desc_score(n_desc, self.eco_lib_dict[cmpn])
                type_score = self.get_type_score(n_ref, self.eco_lib_dict[cmpn])
                rankings_dict[cmpn] = 5*type_score + 5*name_score + 5*kw_score + desc_score

        return rankings_dict

    def get_suggestions(self):
        rankings_dict = self.create_rankings()
        if (len(rankings_dict) > 30):
            sorted_ranking = dict(sorted(rankings_dict.items(), key=lambda item: item[1], reverse=True)[:20])
        else:
            sorted_ranking = dict(sorted(rankings_dict.items(), key=lambda item: item[1], reverse=True))

        suggest_dict = dict()

        for cmpn in list(sorted_ranking):
            if sorted_ranking[cmpn] > 5:
                suggest_dict[cmpn] = dict({'ki_keywords': self.eco_lib_dict[cmpn]['ki_keywords'] if self.eco_lib_dict[cmpn].get('ki_keywords') is not None else '',
                                           'ki_description': self.eco_lib_dict[cmpn]['ki_description'] if self.eco_lib_dict[cmpn].get('ki_description') is not None else '',
                                           'Value': self.eco_lib_dict[cmpn]['Value'] if self.eco_lib_dict[cmpn].get('Value') is not None else '',
                                           'SMD vs. THT': self.eco_lib_dict[cmpn]['SMD vs. THT'] if self.eco_lib_dict[cmpn].get('SMD vs. THT') is not None else '',
                                           'Footprint': self.eco_lib_dict[cmpn]['Footprint'] if self.eco_lib_dict[cmpn].get('Footprint') is not None else '',
                                           'Source': self.eco_lib_dict[cmpn]['Source'] if self.eco_lib_dict[cmpn].get('Source') is not None else '',
                                           'Quantity': self.eco_lib_dict[cmpn]['Quantity'] if self.eco_lib_dict[cmpn].get('Quantity') is not None else ''})

        #ensure at least 3 suggestions show
        if len(suggest_dict.keys()) == 0:
            cmpn1 = list(sorted_ranking.keys())[0]
            cmpn2 = list(sorted_ranking.keys())[1]
            cmpn3 = list(sorted_ranking.keys())[2]
            suggest_dict[cmpn1] = dict({'ki_keywords': self.eco_lib_dict[cmpn1]['ki_keywords'] if self.eco_lib_dict[cmpn1].get('ki_keywords') is not None else '',
                                        'ki_description': self.eco_lib_dict[cmpn1]['ki_description'] if self.eco_lib_dict[cmpn1].get('ki_description') is not None else '',
                                         'Value': self.eco_lib_dict[cmpn1]['Value'] if self.eco_lib_dict[cmpn1].get('Value') is not None else '',
                                         'SMD vs. THT': self.eco_lib_dict[cmpn1]['SMD vs. THT'] if self.eco_lib_dict[cmpn1].get('SMD vs. THT') is not None else '',
                                         'Footprint': self.eco_lib_dict[cmpn1]['Footprint'] if self.eco_lib_dict[cmpn1].get('Footprint') is not None else '',
                                         'Source': self.eco_lib_dict[cmpn1]['Source'] if self.eco_lib_dict[cmpn1].get('Source') is not None else '',
                                         'Quantity': self.eco_lib_dict[cmpn1]['Quantity'] if self.eco_lib_dict[cmpn1].get('Quantity') is not None else ''})
            suggest_dict[cmpn2] = dict({'ki_keywords': self.eco_lib_dict[cmpn2]['ki_keywords'] if self.eco_lib_dict[cmpn2].get('ki_keywords') is not None else '',
                                        'ki_description': self.eco_lib_dict[cmpn2]['ki_description'] if self.eco_lib_dict[cmpn2].get('ki_description') is not None else '',
                                         'Value': self.eco_lib_dict[cmpn2]['Value'] if self.eco_lib_dict[cmpn2].get('Value') is not None else '',
                                         'SMD vs. THT': self.eco_lib_dict[cmpn2]['SMD vs. THT'] if self.eco_lib_dict[cmpn2].get('SMD vs. THT') is not None else '',
                                         'Footprint': self.eco_lib_dict[cmpn2]['Footprint'] if self.eco_lib_dict[cmpn2].get('Footprint') is not None else '',
                                         'Source': self.eco_lib_dict[cmpn2]['Source'] if self.eco_lib_dict[cmpn2].get('Source') is not None else '',
                                         'Quantity': self.eco_lib_dict[cmpn2]['Quantity'] if self.eco_lib_dict[cmpn2].get('Quantity') is not None else ''})
            suggest_dict[cmpn3] = dict({'ki_keywords': self.eco_lib_dict[cmpn3]['ki_keywords'] if self.eco_lib_dict[cmpn3].get('ki_keywords') is not None else '',
                                        'ki_description': self.eco_lib_dict[cmpn3]['ki_description'] if self.eco_lib_dict[cmpn3].get('ki_description') is not None else '',
                                         'Value': self.eco_lib_dict[cmpn3]['Value'] if self.eco_lib_dict[cmpn3].get('Value') is not None else '',
                                         'SMD vs. THT': self.eco_lib_dict[cmpn3]['SMD vs. THT'] if self.eco_lib_dict[cmpn3].get('SMD vs. THT') is not None else '',
                                         'Footprint': self.eco_lib_dict[cmpn3]['Footprint'] if self.eco_lib_dict[cmpn3].get('Footprint') is not None else '',
                                         'Source': self.eco_lib_dict[cmpn3]['Source'] if self.eco_lib_dict[cmpn3].get('Source') is not None else '',
                                         'Quantity': self.eco_lib_dict[cmpn3]['Quantity'] if self.eco_lib_dict[cmpn3].get('Quantity') is not None else ''})
        elif len(suggest_dict.keys()) == 1:
            cmpn2 = list(sorted_ranking.keys())[1]
            cmpn3 = list(sorted_ranking.keys())[2]

            suggest_dict[cmpn2] = dict({'ki_keywords': self.eco_lib_dict[cmpn2]['ki_keywords'] if self.eco_lib_dict[cmpn2].get('ki_keywords') is not None else '',
                                        'ki_description': self.eco_lib_dict[cmpn2]['ki_description'] if self.eco_lib_dict[cmpn2].get('ki_description') is not None else '',
                                         'Value': self.eco_lib_dict[cmpn2]['Value'] if self.eco_lib_dict[cmpn2].get('Value') is not None else '',
                                         'SMD vs. THT': self.eco_lib_dict[cmpn2]['SMD vs. THT'] if self.eco_lib_dict[cmpn2].get('SMD vs. THT') is not None else '',
                                         'Footprint': self.eco_lib_dict[cmpn2]['Footprint'] if self.eco_lib_dict[cmpn2].get('Footprint') is not None else '',
                                         'Source': self.eco_lib_dict[cmpn2]['Source'] if self.eco_lib_dict[cmpn2].get('Source') is not None else '',
                                         'Quantity': self.eco_lib_dict[cmpn2]['Quantity'] if self.eco_lib_dict[cmpn2].get('Quantity') is not None else ''})
            suggest_dict[cmpn3] = dict({'ki_keywords': self.eco_lib_dict[cmpn3]['ki_keywords'] if self.eco_lib_dict[cmpn3].get('ki_keywords') is not None else '',
                                        'ki_description': self.eco_lib_dict[cmpn3]['ki_description'] if self.eco_lib_dict[cmpn3].get('ki_description') is not None else '',
                                         'Value': self.eco_lib_dict[cmpn3]['Value'] if self.eco_lib_dict[cmpn3].get('Value') is not None else '',
                                         'SMD vs. THT': self.eco_lib_dict[cmpn3]['SMD vs. THT'] if self.eco_lib_dict[cmpn3].get('SMD vs. THT') is not None else '',
                                         'Footprint': self.eco_lib_dict[cmpn3]['Footprint'] if self.eco_lib_dict[cmpn3].get('Footprint') is not None else '',
                                         'Source': self.eco_lib_dict[cmpn3]['Source'] if self.eco_lib_dict[cmpn3].get('Source') is not None else '',
                                         'Quantity': self.eco_lib_dict[cmpn3]['Quantity'] if self.eco_lib_dict[cmpn3].get('Quantity') is not None else ''})
        elif len(suggest_dict.keys()) == 2:
            cmpn3 = list(sorted_ranking.keys())[2]

            suggest_dict[cmpn3] = dict({'ki_keywords': self.eco_lib_dict[cmpn3]['ki_keywords'] if self.eco_lib_dict[cmpn3].get('ki_keywords') is not None else '',
                                        'ki_description': self.eco_lib_dict[cmpn3]['ki_description'] if self.eco_lib_dict[cmpn3].get('ki_description') is not None else '',
                                         'Value': self.eco_lib_dict[cmpn3]['Value'] if self.eco_lib_dict[cmpn3].get('Value') is not None else '',
                                         'SMD vs. THT': self.eco_lib_dict[cmpn3]['SMD vs. THT'] if self.eco_lib_dict[cmpn3].get('SMD vs. THT') is not None else '',
                                         'Footprint': self.eco_lib_dict[cmpn3]['Footprint'] if self.eco_lib_dict[cmpn3].get('Footprint') is not None else '',
                                         'Source': self.eco_lib_dict[cmpn3]['Source'] if self.eco_lib_dict[cmpn3].get('Source') is not None else '',
                                         'Quantity': self.eco_lib_dict[cmpn3]['Quantity'] if self.eco_lib_dict[cmpn3].get('Quantity') is not None else ''})
        
        return suggest_dict

    def is_drop_in(self, o_name, n_cmpn_dict):
        return False
    '''
        if o_name in n_cmpn_dict["Drop-in replacement"].split(",") or o_name in n_cmpn_dict["Drop-in replacement"].split(" "):
            if self.n_cmpn_dict is None:
                return False
            if self.n_cmpn_dict["Footprint"] != '' and (self.n_cmpn_dict["Footprint"] is not None) and self.n_cmpn_dict["Footprint"] == self.new_component["Footprint"]:
                return True
        else:
            return False
    '''

    def split_on_letter(self, s):
        '''
            Helper function for getting values for passive components - identifying numeric and letter values
        '''
        i = 0
        for i,c in enumerate(s):
            if not c.isdigit() and c!= '.':
                break
        
        if i >= 1:
            if s[i].isdigit():
                number=s[:i+1]
            else:
                number=s[:i]
        elif i == 0 and len(s) > 0:
            if s[0].isdigit():
                number = s[0]
            else:
                number = ''
        else:
            number = ''
        unit=s[i:]

        return number, unit


    def get_num_value(self,value_txt):
        '''
            Multiplying values by the abbreviated multiple
        '''
        
        val_num, val_char = self.split_on_letter(value_txt)

        if len(val_num) < 1:
            return float("inf")
        elif len(val_char) < 1:
            return float(val_num)
        elif val_char[0]=='M':
            return float(val_num) * 1000000
        elif val_char[0]=='k':
            return float(val_num) * 1000
        elif val_char[0]=='K':
            return float(val_num) * 1000
        elif val_char[0]=='m':
            return float(val_num) * 0.001
        elif val_char[0]=='u':
            return float(val_num) * 0.000001
        elif val_char[0]=='n':
            return float(val_num) * 0.000000001
        elif val_char[0]=='p':
            return float(val_num) * 0.000000000001
        elif val_char[0]== 'O':
            return float(val_num) * 1.00
        elif val_char[0]== 'o':
            return float(val_num) * 1.00
        elif val_char[0]== 'F':
            return float(val_num) * 1.00
        elif val_char[0]== 'f':
            return float(val_num) * 1.00
        return float(val_num)

    def is_equivalent_value(self,val1_str, val2_str):

        val1 = self.get_num_value(val1_str)
        val2 = self.get_num_value(val2_str)

        if val1 == val2:
            return True
        else:
            return False


    def is_exact_match(self, o_name, n_cmpn_dict):
        if "Exact match" not in n_cmpn_dict.keys():
            return False
        
        if o_name in n_cmpn_dict["Exact match"].split(",") or o_name in n_cmpn_dict["Exact match"].split(" "):
            # do additional checks based on types
            if (self.new_component["reference"] is not None) and self.new_component["reference"] != '' and self.new_component["reference"][0] in "RCYD":
                if self.new_component["value"] == n_cmpn_dict["Value"]:
                    return True
                elif self.is_equivalent_value(self.new_component["value"], n_cmpn_dict["Value"]):
                    return True
                else:
                    return False
            else:
                return True
        else:
            return False

    def find_match_type(self):
        o_name = self.new_component["lib_id"].split(":")[1]

        for cmpn in self.eco_lib_dict:
            if self.is_exact_match(o_name, self.eco_lib_dict[cmpn]):
                if self.new_component["Footprint"] != '' and (self.new_component["Footprint"] is not None) and self.new_component["Footprint"] == self.eco_lib_dict[cmpn]["Footprint"]:
                    return "exact match", cmpn, self.eco_lib_dict[cmpn]
                else:
                    return "diff fp", cmpn, self.eco_lib_dict[cmpn]
            elif self.is_drop_in(o_name, self.eco_lib_dict[cmpn]):
                if(cmpn.split("-")[0] == "Subcircuit"):
                    return "subcircuit", cmpn, self.eco_lib_dict[cmpn]
                else:
                    return "drop-in", cmpn, self.eco_lib_dict[cmpn]
        return "rank", None, None

