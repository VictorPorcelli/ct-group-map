import pandas as pd
import json
from shapely.geometry import shape, Point, Polygon, MultiPolygon

from shapely.ops import nearest_points
from shapely import wkt
import geopandas as gpd
import geopy.distance

import random
import math
import numpy as np

#get demographic data to be used in creating a score for similarity between CTs
income_data = pd.read_csv("income_data_boroct_03.20.22.csv")
gentr_data = pd.read_csv("Gentrification Data by Census Tract_20220322.csv")
del income_data['Unnamed: 0']

merged_data = pd.merge(income_data, gentr_data, how = "outer", left_on = 'BoroCT', right_on = 'censustract', copy = False)
del merged_data['censustract']

merged_data['2011 Household Median Income'] = merged_data['2011 Household Median Income'].str.replace(',','')
merged_data['2011 Household Median Income'] = merged_data['2011 Household Median Income'].str.replace('+','')

clean_inc = merged_data[merged_data['2011 Household Median Income'] != '-']['2011 Household Median Income']
clean_inc = clean_inc.astype('float64')

inc_mean = clean_inc.mean(axis = 0, skipna = True)
inc_sd = clean_inc.std(axis = 0, skipna = True)

rent_mean = merged_data['changeinrent0016'].mean(axis = 0, skipna = True)
rent_sd = merged_data['changeinrent0016'].std(axis = 0, skipna = True)

gentr_mean = merged_data['gentrificationcomposite'].mean(axis = 0, skipna = True)
gentr_sd = merged_data['gentrificationcomposite'].std(axis = 0, skipna = True)


with open("2010_censustracts.geojson") as f:
    ct_js = json.load(f)

with open("City Council Districts.geojson") as g:
    cd_js = json.load(g)

cds_and_tracts = []
file = open("cds_and_tracts.csv","r")

for line in file:
    if line.find("Council District") == -1:
        line = line.replace("\n","")
        line = line.split(",")
        
        cd = line[0]
        cts = line[1].strip().split(" ")

        cds_and_tracts.append([cd,cts])

file.close()

#remove population stuff and implement a score method

def get_score(ct1, ct2):
    score = 0.0
    inc_comp, rent_comp, gentr_comp = 0.0, 0.0, 0.0
    ct1_inc, ct1_rent, ct1_gentr, ct2_inc, ct2_rent, ct2_gentr = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    try:
        ct1_inc = float(merged_data[merged_data['BoroCT'] == int(ct1)]['2011 Household Median Income'])
    except:
        pass
    try:
        ct2_inc = float(merged_data[merged_data['BoroCT'] == int(ct2)]['2011 Household Median Income'])
    except:
        pass
        
    try:
        ct1_rent = float(merged_data[merged_data['BoroCT'] == int(ct1)]['changeinrent0016'])
    except:
        pass

    try:
        ct2_rent = float(merged_data[merged_data['BoroCT'] == int(ct2)]['changeinrent0016'])
    except:
        pass

    try:
        ct1_gentr = float(merged_data[merged_data['BoroCT'] == int(ct1)]['gentrificationcomposite'])
    except:
        pass
        
    try:
        ct2_gentr = float(merged_data[merged_data['BoroCT'] == int(ct2)]['gentrificationcomposite'])
    except:
        pass

    if ct1_inc != 0.0 and ct2_inc != 0.0:
        inc_comp = ((ct1_inc -inc_mean)/inc_sd - (ct2_inc -inc_mean)/inc_sd) ** 2

    if ct1_rent != 0.0 and ct2_rent != 0.0:
        rent_comp = ((ct1_rent -rent_mean)/rent_sd - (ct2_rent -rent_mean)/rent_sd) ** 2

    if ct1_gentr != 0.0 and ct2_gentr != 0.0:
        gentr_comp = ((ct1_gentr -gentr_mean)/gentr_sd - (ct2_gentr -gentr_mean)/gentr_sd) ** 2

    score_comps = [inc_comp, rent_comp, gentr_comp]

    x = 0
    for comp in score_comps:
        if comp != 0.0:
            score += comp
            x +=1

    if x != 0:
        score = score/x
    else:
        score = 999.99

    return score

def get_aggr_score(cluster):
    cluster = cluster[1:]
    aggr_score = 0.0
    num_scores = 0
    for ct in cluster:
        for ct2 in cluster:
            if ct != ct2:
                temp_score = get_score(ct, ct2)
                if temp_score != 0.0:
                    aggr_score+=temp_score
                    num_scores +=1

    if num_scores != 0:
        aggr_score = aggr_score/num_scores
    else:
        aggr_score = 999.99

    return aggr_score

def get_borders(start_ct, all_cts, exclusions):
    border_cts = []
    
    for ct_feature in ct_js['features']:
        ct = str(ct_feature['properties']['BoroCT2010'])
        if ct == start_ct:
            start_poly = shape(ct_feature['geometry'])
    for ct_feature in ct_js['features']:
        ct2 = str(ct_feature['properties']['BoroCT2010'])
        if (ct2 in all_cts) and (ct2 not in exclusions):
            ct_poly = shape(ct_feature['geometry'])
            if start_poly.intersects(ct_poly):
                border_cts.append(ct2)

    return border_cts

def get_distances(start_ct, all_cts, exclusions):
    distances = []
    for ct_feature in ct_js['features']:
        tract = str(ct_feature['properties']['BoroCT2010'])
        if tract == start_ct:
            start_poly = shape(ct_feature['geometry'])
            start_center = start_poly.centroid
    for ct_feature in ct_js['features']:
        tract2 = str(ct_feature['properties']['BoroCT2010'])
        if tract2 not in exclusions and tract2 in all_cts:
            new_poly = shape(ct_feature['geometry'])
            new_center = new_poly.centroid

            dist = float(str(geopy.distance.geodesic((new_center.y, new_center.x),(start_center.y, start_center.x))).replace(" km",""))
            dist_miles = dist * 0.621371

            distances.append([tract2, dist_miles])

    return distances

def get_best_cluster(start_ct, border_cts, border_cts2, border_cts3):
    cluster = []
    smallest_diff = 999999.99*999999.99
    if len(border_cts3) == 0:
        for second_ct in border_cts:
            second_borders = []
            for val in border_cts2:
                if val[0] == second_ct:
                    second_borders = val[1]
            
            for third_ct in second_borders:
                first_second = get_score(start_ct, second_ct)
                first_third = get_score(start_ct, third_ct)
                second_third = get_score(third_ct, second_ct)

                avg_score = (first_second + first_third + second_third)/3

                if avg_score < smallest_diff:
                    smallest_diff = avg_score
                    cluster = [start_ct, second_ct, third_ct]

        return cluster
                
    else:
        for second_ct in border_cts:
            second_borders = []
            for val in border_cts2:
                if val[0] == second_ct:
                    second_borders = val[1]
            
            for third_ct in second_borders:
                third_borders = []
                for val in border_cts3:
                    if val[0] == third_ct:
                        third_borders = val[1]

                for val in third_borders:
                    if val == second_ct:
                        third_borders.remove(val)
                    
                for fourth_ct in third_borders:
                    first_second = get_score(start_ct, second_ct)
                    first_third = get_score(start_ct, third_ct)
                    first_fourth = get_score(start_ct, fourth_ct)

                    second_third = get_score(third_ct, second_ct)
                    second_fourth = get_score(fourth_ct, second_ct)

                    third_fourth = get_score(third_ct, fourth_ct)

                    avg_score = (first_second + first_third + first_fourth + second_third + second_fourth + third_fourth)/6

                    if avg_score < smallest_diff:
                        smallest_diff = avg_score
                        cluster = [start_ct, second_ct, third_ct, fourth_ct]

        return cluster

def gen_cluster(cd_cts, can_be_three):
    cd = cd_cts[0]
    cts = cd_cts[1]
    cluster = []

    #pick a random ct to start at
    start_index = random.randint(0,len(cts)-1)
    start_ct = cts[start_index]

    #find all cts that border it
    border_cts = get_borders(start_ct, cts, [start_ct])

    if len(border_cts) == 0:
        return []
    else:
        border_cts2 = []
        for ct in border_cts:
            borders = get_borders(ct, cts, [start_ct, ct])
            if len(borders) > 0:
                border_cts2.append([ct, borders])

        if len(border_cts2) == 0:
            return []
        else:
            border_cts3 = []
            for ct in border_cts2:
                temp_second = ct[0]
                temp_borders = ct[1]

                for ct2 in temp_borders:
                    borders = get_borders(ct2, cts, [start_ct, temp_second, ct2])
                    if len(borders) > 0:
                        border_cts3.append([ct2, borders])

            if len(border_cts3) == 0:
                if can_be_three:
                    cluster = get_best_cluster(start_ct, border_cts, border_cts2, [])
                    return cluster
                else:
                    return []
            else:
                cluster = get_best_cluster(start_ct, border_cts, border_cts2, border_cts3)
                return cluster

def gen_cluster2(cd_cts):
    cd = cd_cts[0]
    cts = cd_cts[1]
    cluster = []

    for ct in cts:
        borders = get_borders(ct, cts, [ct])
        for second_ct in borders:
            borders2 = get_borders(second_ct, cts, [ct, second_ct])
            if len(borders2) > 0:
                cluster = [ct, second_ct, borders2[0]]
    if cluster == []:
        for ct in cts:
            borders = get_borders(ct, cts, [ct])
            if len(borders) > 0:
                cluster = [ct, borders[0]]

    return cluster
                
def assign_cluster(leftover_cts, all_cts):
    cd = leftover_cts[0]

    num_tries = 0
    clusters = []
    new_cluster = ["","","",""]
    
    while len(new_cluster) > 0 and num_tries < 100:
        try:
            new_cluster = gen_cluster(leftover_cts, True)
            if len(new_cluster) != 0:
                new_leftover_cts = [cd,[]]
                for val in leftover_cts[1]:
                    if val in new_cluster:
                        pass
                    else:
                        new_leftover_cts[1].append(val)
                leftover_cts = new_leftover_cts
                new_cluster.insert(0,cd)
                clusters.append(new_cluster)

                new_ct_list = [cd,[]]
                for ct in leftover_cts[1]:
                    if ct in new_cluster:
                        pass
                    else:
                        new_ct_list[1].append(ct)

                leftover_cts = new_ct_list
            else:
                num_tries += 1
        except:
            num_tries = 200

    if len(clusters) > 0:
        return clusters
    else:
        num_tries = 0
        new_cluster = ["","","",""]
        
        while len(new_cluster) > 0 and num_tries < 100:
            try:
                new_cluster = gen_cluster2(leftover_cts)
                if len(new_cluster) != 0:
                    new_leftover_cts = [cd,[]]
                    for val in leftover_cts[1]:
                        if val in new_cluster:
                            pass
                        else:
                            new_leftover_cts[1].append(val)
                    leftover_cts = new_leftover_cts
                    new_cluster.insert(0,cd)
                    clusters.append(new_cluster)

                    new_ct_list = [cd,[]]
                    for ct in leftover_cts[1]:
                        if ct in new_cluster:
                            pass
                        else:
                            new_ct_list[1].append(ct)

                    leftover_cts = new_ct_list
                else:
                    num_tries += 1
            except:
                num_tries = 200

        return clusters

def sort_dist(arr, dist_index):
    sort_values = []
    for value in arr:
        sort_values.append(value[dist_index])
    sort_values.sort()
    
    sorted_arr = []
    for value in sort_values:
        for item in arr:
            if item[dist_index] == value:
                sorted_arr.append(item)

    return sorted_arr

def assign_cluster2(leftover_cts, possible_matches):
    cd = leftover_cts[0]
    leftovers = leftover_cts[1]

    matches = []
    for ct in leftovers:
        for ct_feature in ct_js['features']:
            if str(ct_feature['properties']['BoroCT2010']) == ct:
                ct_poly = shape(ct_feature['geometry'])

        close_cts = []
        for ct_feature in ct_js['features']:
            ct2 = str(ct_feature['properties']['BoroCT2010'])
            if ct2 in possible_matches and ct2 != ct:
                ct_poly2 = shape(ct_feature['geometry'])
                if ct_poly.intersects(ct_poly2):
                    close_cts.append(ct2)

        if close_cts != []:
            matches.append([ct, close_cts])

    return matches

def assign_cluster3(leftover_cts, possible_matches):
    matches = []
    cd = leftover_cts[0]
    leftovers = leftover_cts[1]
    two_closest = []
    for ct in leftovers:
        for ct_feature in ct_js['features']:
            if str(ct_feature['properties']['BoroCT2010']) == ct:
                ct_poly = shape(ct_feature['geometry'])

        ct_center = Point(ct_poly.centroid)
        two_closest = []
        #can use get distances function here
        for ct_feature in ct_js['features']:
            ct3 = str(ct_feature['properties']['BoroCT2010'])
            if ct3 in possible_matches and ct3 != ct:
                ct_poly3 = shape(ct_feature['geometry'])
                ct_center3 = Point(ct_poly3.centroid)

                dist = float(str(geopy.distance.geodesic((ct_center.y, ct_center.x),(ct_center3.y, ct_center3.x))).replace(" km",""))
                dist_miles = dist * 0.621371
                        
                if len(two_closest) < 2:
                    two_closest.append([ct3, dist_miles])
                    if len(two_closest) == 2:
                        two_closest = sort_dist(two_closest, 1)
                elif dist_miles < float(two_closest[1][1]):
                    two_closest.remove(two_closest[1])
                    two_closest.append([ct3, dist_miles])
                    two_closest = sort_dist(two_closest, 1)
        if len(two_closest) == 2:
            matches.append([ct, [two_closest[0][0], two_closest[1][0]]])
        elif two_closest != []:
            matches.append([ct, [two_closest[0][0]]])

    return matches

min_size = 0
while min_size < 6:
    clusters = []
    cluster_sizes = []
    for i in cds_and_tracts:
        cd = i[0]
        cts_list = i
        original_list = cts_list
        new_cluster = ["","","",""]
        num_clusters = 0
        added_clusters = []
        
        while len(new_cluster) > 0 and len(cts_list[1])>1:
            new_cluster = gen_cluster(cts_list, True)
            if len(new_cluster) != 0:
                new_ct_list = [cd,[]]
                for val in cts_list[1]:
                    if val in new_cluster:
                        pass
                    else:
                        new_ct_list[1].append(val)
                cts_list = new_ct_list
                if new_cluster != []:
                    new_cluster.insert(0,cd)
                    clusters.append(new_cluster)
                    added_clusters.append(new_cluster)
                    num_clusters+=1
        
        new_clusters = ["","","",""]
        while len(new_clusters) > 0 and len(cts_list) > 2:
            new_clusters = assign_cluster(cts_list, original_list)
            if new_clusters != []:
                for cluster in new_clusters:
                    if cluster != []:
                        clusters.append(cluster)
                        added_clusters.append(new_cluster)
                        num_clusters+=1
                
                new_ct_list = [cd,[]]
                for ct in cts_list[1]:
                    found = False
                    for cluster in new_clusters:
                        if ct in cluster:
                            found = True
                    if found == False:
                        new_ct_list[1].append(ct)

                cts_list = new_ct_list

        new_cluster = ["","","",""]
        while len(new_cluster) > 0 and len(cts_list[1])>1:
            new_cluster = gen_cluster2(cts_list)
            if len(new_cluster) != 0:
                new_ct_list = [cd,[]]
                for val in cts_list[1]:
                    if val in new_cluster:
                        pass
                    else:
                        new_ct_list[1].append(val)
                cts_list = new_ct_list
                if new_cluster != []:
                    new_cluster.insert(0,cd)
                    clusters.append(new_cluster)
                    added_clusters.append(new_cluster)
                    num_clusters+=1

        clustered_cts = []
        for cluster in added_clusters:
            for ct in cluster:
                clustered_cts.append(ct)

        tries = 0
        while ((len(cts_list[1]) >0) and (tries<50)):
            closest_cts = assign_cluster2(cts_list, clustered_cts)
            for val in closest_cts:
                ct = val[0]
                if len(val[1]) > 1:
                    possible_clusters = []
                    all_matches = val[1]

                    for cluster in clusters:
                        for match in all_matches:
                            if match in cluster:
                                if cluster not in possible_clusters:
                                    possible_clusters.append(cluster)
                    
                    if len(possible_clusters) > 1:
                        smallest_diff = 999999.99
                        cluster_pick = possible_clusters[0]
                        for cluster in possible_clusters:
                            score = get_aggr_score(cluster)
                            if score<smallest_diff:
                                smallest_diff = score
                                cluster_pick = cluster

                        clusters[clusters.index(cluster_pick)].append(ct)
                        cts_list[1].remove(ct)
                        clustered_cts.append(ct)
                    elif len(possible_clusters) == 1:
                        clusters[clusters.index(possible_clusters[0])].append(ct)
                        cts_list[1].remove(ct)
                        clustered_cts.append(ct)
                elif len(val[1]) == 1:
                    for cluster in clusters:
                        if val[1][0] in cluster:
                            clusters[clusters.index(cluster)].append(ct)
                            cts_list[1].remove(ct)
                            clustered_cts.append(ct)
            tries+=1

        while(len(cts_list[1]) >0):
            closest_cts = assign_cluster3(cts_list, clustered_cts)
            #check if some of this is for assign_cluster2 stuff
            for val in closest_cts:
                ct = val[0]
                if len(val[1]) > 1:
                    possible_clusters = []
                    all_matches = val[1]

                    for cluster in clusters:
                        for match in all_matches:
                            if match in cluster:
                                if cluster not in possible_clusters:
                                    possible_clusters.append(cluster)
                    
                    if len(possible_clusters) > 1:
                        smallest_diff = 999999.99
                        cluster_pick = possible_clusters[0]
                        for cluster in possible_clusters:
                            score = get_aggr_score(cluster)
                            if score<smallest_diff:
                                smallest_diff = score
                                cluster_pick = cluster

                        clusters[clusters.index(cluster_pick)].append(ct)
                        cts_list[1].remove(ct)
                        clustered_cts.append(ct)
                    elif len(possible_clusters) == 1:
                        clusters[clusters.index(possible_clusters[0])].append(ct)
                        cts_list[1].remove(ct)
                        clustered_cts.append(ct)
                elif len(val[1]) == 1:
                    for cluster in clusters:
                        if val[1][0] in cluster:
                            clusters[clusters.index(cluster)].append(ct)
                            cts_list[1].remove(ct)
                            clustered_cts.append(ct)

        
        cluster_sizes.append(num_clusters)

    min_size = 20
    for size in cluster_sizes:
        if size < min_size:
            min_size = size
    print(min_size)
    
outfile = open("ct_clusters.csv","w")
outfile.write("CD, CTs in Cluster \n")

count_cts = 0
check_vals = []
for cluster in clusters:
    outfile.write(str(cluster[0])+",")
    newstr = ""
    for val in cluster[1:]:
        newstr+=str(val)+" "
        count_cts+=1
        if val in check_vals:
            print("Error: repeated tract: "+str(val))
        check_vals.append(val)
    outfile.write(newstr+"\n")

outfile.close()

print(count_cts)
