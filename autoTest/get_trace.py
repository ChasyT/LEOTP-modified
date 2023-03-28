# The MIT License (MIT)
#
# Copyright (c) 2020 ETH Zurich
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import sys
#sys.path.append('../hypatia_tools/')
from hypatia_tools.distance_tools import *
from hypatia_tools.graph_tools import *
from hypatia_tools.read_isls import *
from hypatia_tools.read_ground_stations import *
from hypatia_tools.read_tles import *
import exputil
import tempfile
import numpy as np
import matplotlib.pyplot as plt

isl_trace_dir = "./hypatia_trace/starlink_550_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"
relay_only_trace_dir = "./hypatia_trace/starlink_550_isls_none_ground_stations_top_100_algorithm_free_one_only_gs_relays"
#"../../../paper/satellite_networks_state/gen_data/starlink_550_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"

#city_1 and city_2 are id in gs_100 list
#return (max_midnode_num,total_midnode_num,links_params)
#links_params in a list of dictionary, each element has key "topo" "rtt" "loss" and "bw"

def get_city_distance(src,dst,route_algorithm="with_isl"):
    satellite_network_dir = isl_trace_dir if route_algorithm=="with_isl" else relay_only_trace_dir
    ground_stations = read_ground_stations_extended(satellite_network_dir + "/ground_stations.txt")
    city1 = ground_stations[src]
    city2 = ground_stations[dst]
    distance_m = geodesic_distance_m_between_ground_stations(city1,city2)
    return distance_m/1000

def get_trace(#base_output_dir,         #do not set bw and loss
                         city1,   #<100
                         city2,   #<100
                         #satgenpy_dir_with_ending_slash,
                         start_ts_s = 0,
                         duration_s = 600,    #<=600
                         route_algorithm = "with_isl",
                         dynamic_state_update_interval_ms = 1000,
                         simulation_end_time_s = 600):         #to find fstate                    

    # Local shell
    #local_shell = exputil.LocalShell()
    if route_algorithm == "with_isl":
        satellite_network_dir = isl_trace_dir
    else:
        satellite_network_dir = relay_only_trace_dir

    satellite_num = 1584
    src = city1 + satellite_num
    dst = city2 + satellite_num
    # Dynamic state dir can be inferred
    satellite_network_dynamic_state_dir = "%s/dynamic_state_%dms_for_%ds" % (
        satellite_network_dir, dynamic_state_update_interval_ms, simulation_end_time_s
    )

    # Default output dir assumes it is done manual
    #pdf_dir = base_output_dir + "/pdf"
    #data_dir = base_output_dir + "/data"
    #local_shell.make_full_dir(pdf_dir)
    #local_shell.make_full_dir(data_dir)

    # Variables (load in for each thread such that they don't interfere)
    ground_stations = read_ground_stations_extended(satellite_network_dir + "/ground_stations.txt")
    tles = read_tles(satellite_network_dir + "/tles.txt")
    satellites = tles["satellites"]
    list_isls = read_isls(satellite_network_dir + "/isls.txt", len(satellites))
    epoch = tles["epoch"]
    description = exputil.PropertiesConfig(satellite_network_dir + "/description.txt")

    # Derivatives
    simulation_start_time_ns = start_ts_s * 1000 * 1000 * 1000
    simulation_end_time_ns = (start_ts_s + duration_s) * 1000 * 1000 * 1000
    dynamic_state_update_interval_ns = dynamic_state_update_interval_ms * 1000 * 1000
    max_gsl_length_m = exputil.parse_positive_float(description.get_property_or_fail("max_gsl_length_m"))
    max_isl_length_m = exputil.parse_positive_float(description.get_property_or_fail("max_isl_length_m"))

    # Write data file

    #data_path_filename = data_dir + "/networkx_path_" + str(src) + "_to_" + str(dst) + ".txt"
    #with open(data_path_filename, "w+") as data_path_file:

        # For each time moment
    fstate = {}
    current_path = []
    rtt_ns_list = []
    node_list = []
    max_path_length = 0
    links_params = []
    midnode_id_map_dict = {}
    global_midnode_id = 0
    #first_satellites = [] #connect with h1
    #last_satellites = []  #connect with h2
    isls = []
    for t in range(simulation_start_time_ns, simulation_end_time_ns, dynamic_state_update_interval_ns):
        links_param = {}
        with open(satellite_network_dynamic_state_dir + "/fstate_" + str(t) + ".txt", "r") as f_in:
            for line in f_in:
                spl = line.split(",")
                current = int(spl[0])
                destination = int(spl[1])
                next_hop = int(spl[2])
                fstate[(current, destination)] = next_hop

            # Calculate path length
            path_there = get_path(src, dst, fstate)
            #print(path_there)
            path_back = get_path(dst, src, fstate)
            if path_there is not None and path_back is not None:
                length_src_to_dst_m = compute_path_length_without_graph(path_there, epoch, t, satellites,
                                                                        ground_stations, list_isls,
                                                                        max_gsl_length_m, max_isl_length_m)
                length_dst_to_src_m = compute_path_length_without_graph(path_back, epoch, t,
                                                                        satellites, ground_stations, list_isls,
                                                                        max_gsl_length_m, max_isl_length_m)
                rtt_ns = (length_src_to_dst_m + length_dst_to_src_m) * 1000000000.0 / 299792458.0
            else:
                length_src_to_dst_m = 0.0
                length_dst_to_src_m = 0.0
                rtt_ns = 0.0

            # Add to RTT list
            rtt_ns_list.append((t, rtt_ns))
            
            # Only if there is a new path, print new path
            new_path = get_path(src, dst, fstate)
            #print(new_path)
            if True:	#current_path != new_path

                # This is the new path
                current_path = new_path

                #calculate hop rtt
                hop_rtt_ms_list = []
                path_length = len(current_path)
                for node in current_path[1:-1]:
                	if node not in midnode_id_map_dict.keys(): 
                            global_midnode_id += 1
                            midnode_id_map_dict[node] = global_midnode_id
                max_path_length = max(max_path_length,path_length)
                for i in range(path_length-1):
                    node1 = current_path[i]
                    node2 = current_path[i+1]
                    hop_length_src_to_dst_m = compute_path_length_without_graph([node1,node2], epoch, t, satellites,
                                                                        ground_stations, list_isls,
                                                                        max_gsl_length_m, max_isl_length_m)
                    hop_length_dst_to_src_m = compute_path_length_without_graph([node2,node1], epoch, t, satellites,
                                                                        ground_stations, list_isls,
                                                                        max_gsl_length_m, max_isl_length_m)
                    hop_rtt_ns = (hop_length_src_to_dst_m + hop_length_dst_to_src_m) * 1000000000.0 / 299792458.0
                    hop_rtt_ms = hop_rtt_ns / 1e6
                    hop_rtt_ms_list.append(round(hop_rtt_ms,2))
                renamed_current_path = list(map(lambda x:midnode_id_map_dict[x],current_path[1:-1]))
                if (0,renamed_current_path[0]) not in isls:
                    isls.append((0,renamed_current_path[0]))
                if (renamed_current_path[-1],-1) not in isls:
                    isls.append((renamed_current_path[-1],-1))
                for i in range(path_length-3):
                    if (renamed_current_path[i],renamed_current_path[i+1]) not in isls and (renamed_current_path[i+1],renamed_current_path[i]) not in isls :
                        isls.append((renamed_current_path[i],renamed_current_path[i+1]))
                links_param["topo"] = renamed_current_path 
                links_param["rtt"] = [50]+hop_rtt_ms_list+[50]
                links_param["loss"] = []
                links_param["bw"] = []
                links_params.append(links_param)
                # Write change nicely to the console
                #prinstep=t("Change at t=" + str(t) + " ns (= " + str(t / 1e9) + " seconds)")
                #print("  > Path..... " + (" -- ".join(list(map(lambda x: str(x), current_path)))
                                          #if current_path is not None else "Unreachable"))
                #print("  > Hop RTT... "+ (" -- ".join(list(map(lambda x: "%.2fms"%(x),hop_rtt_ms_list)))))
                #print("  > Length... " + str(length_src_to_dst_m + length_dst_to_src_m) + " m")
                #print("  > RTT...... %.2f ms" % (rtt_ns / 1e6))
                #print("")

                # Write to path file
                #data_path_file.write(str(t) + "," + ("-".join(list(map(lambda x: str(x), current_path)))
                                                    # if current_path is not None else "Unreachable") + "\n")

    #print("  > Total node number... %d"%(len(node_list)))
    #print("  > Max path length... %d"%(max_path_length)path_length)
    #print("")
    #total_midnode_num = len(node_list)
    
    return max_path_length-2,global_midnode_id,isls,links_params
    
    # Write data file
    #data_filename = data_dir + "/networkx_rtt_" + str(src) + "_to_" + str(dst) + ".txt"
    #with open(data_filename, "w+") as data_file:
    #    for i in range(len(rtt_ns_list)):
    #        data_file.write("%d,%.10f\n" % (rtt_ns_list[i][0], rtt_ns_list[i][1]))

    # Make plot
    '''
    pdf_filename = pdf_dir + "/time_vs_networkx_rtt_" + str(src) + "_to_" + str(dst) + ".pdf"
    tf = tempfile.NamedTemporaryFile(delete=False)
    tf.close()
    local_shell.copy_file(satgenpy_dir_with_ending_slash + "plot/plot_time_vs_networkx_rtt.plt", tf.name)
    local_shell.sed_replace_in_file_plain(tf.name, "[OUTPUT-FILE]", pdf_filename)
    local_shell.sed_replace_in_file_plain(tf.name, "[DATA-FILE]", data_filename)
    local_shell.perfect_exec("gnuplot " + tf.name)
    print("Produced plot: " + pdf_filename)
    local_shell.remove(tf.name)
    '''

def get_bw(bw_max,start_ts,end_ts,current_ts):
    #c = 4*bw_max/((end_ts-start_ts)**2)
    c = 2*bw_max/((end_ts-start_ts)**2)
    mean_bw = round(c*(end_ts-current_ts)*(current_ts-start_ts),2) + bw_max/2
    bw = mean_bw
    if mean_bw > 5:
        if current_ts%2 == 0:
            bw = mean_bw + 0.5
        else:
            bw = mean_bw - 0.5
    return bw

def add_bw_fluct(links_params,downlink_change_ts,downlink_bw,uplink_change_ts,uplink_bw):
    for i in range(len(downlink_change_ts)-1):
        start_ts = downlink_change_ts[i]
        end_ts = downlink_change_ts[i+1]
        #print(start_ts,end_ts)
        #c = 4*downlink_bw/((end_ts-start_ts)**2)
        for j in range(start_ts,end_ts):
            #links_params[j]["bw"][1] = round(c*(end_ts-j)*(j-start_ts),2)
            links_params[j]["bw"][1] = get_bw(downlink_bw, start_ts, end_ts, j)
    for i in range(len(uplink_change_ts)-1):
        start_ts = uplink_change_ts[i]
        end_ts = uplink_change_ts[i+1]
        #print(start_ts,end_ts)
        #c = 4*uplink_bw/((end_ts-start_ts)**2)
        for j in range(start_ts,end_ts):
            #links_params[j]["bw"][-2] = round(c*(end_ts-j)*(j-start_ts),2)
            links_params[j]["bw"][-2] = get_bw(uplink_bw, start_ts, end_ts, j)
    return links_params

def get_complete_trace(    #set bw and loss
            origin_trace,   #only include rtt trace
            uplink_bw = 5,
            downlink_bw = 20,
            isl_bw = 20,
            ground_link_bw = 20,
            uplink_loss = 0.1,
            downlink_loss = 0.1,
            isl_loss = 0.1,
            ground_link_loss= 0,
            ground_link_rtt = 50,
            bw_fluctuation = False):
    #max_midnode_num,total_midnode_num,isls,links_params = get_trace(city1,city2,start_ts_s,duration_s)
    max_midnode_num,total_midnode_num,isls,links_params = origin_trace
    downlink_change_ts = []
    uplink_change_ts = []
    prev_downlink_sat_id = -2
    prev_uplink_sat_id = -2
    for idx,links_param in enumerate(links_params):
        sats = len(links_param["topo"])
        downlink_sat_id = links_param["topo"][0]        #get downlink change time
        uplink_sat_id = links_param["topo"][-1]
        if downlink_sat_id != prev_downlink_sat_id:
            downlink_change_ts.append(idx)
            prev_downlink_sat_id = downlink_sat_id
            
        if uplink_sat_id != prev_uplink_sat_id:
            uplink_change_ts.append(idx)
            prev_uplink_sat_id = uplink_sat_id

        links_param["loss"] = [ground_link_loss,downlink_loss]+[isl_loss]*(sats-1)+[uplink_loss,ground_link_loss]
        links_param["bw"] = [ground_link_bw,downlink_bw]+[isl_bw]*(sats-1)+[uplink_bw,ground_link_bw]
        links_param["rtt"][0] = ground_link_rtt
        links_param["rtt"][-1] = ground_link_rtt
    downlink_change_ts.append(len(links_params))
    uplink_change_ts.append(len(links_params))
    #print(downlink_change_ts)
    if bw_fluctuation:
        #print("fuck")
        links_params = add_bw_fluct(links_params,downlink_change_ts,downlink_bw,uplink_change_ts,uplink_bw)

    return  max_midnode_num,total_midnode_num,isls,links_params



def add_bw_fluct_relay_only(links_params,downlink_bw):
    downlink_infos = [] 
    for links_param in links_params:
        current_downlink_info = {}  # {(gs_id,sat_id):(start_ts,end_ts), ... ,}
        current_downlink_info[(0,links_param["topo"][0])] = [-1,-1]
        for i in range(len(links_param["topo"])):
            if i%2==1:
                current_downlink_info[(links_param["topo"][i],links_param["topo"][i+1])] = [-1,-1]
        downlink_infos.append(current_downlink_info)
    # fill start_ts
    for i,downlink_info in enumerate(downlink_infos):
        for down_link_pair in downlink_info.keys():
            if i==0 or down_link_pair not in downlink_infos[i-1].keys():
                downlink_info[down_link_pair][0] = i
            else:
                downlink_info[down_link_pair][0] = downlink_infos[i-1][down_link_pair][0]
    # fill end_ts
    for i in range(len(downlink_infos)-1,-1,-1):
        for down_link_pair in downlink_infos[i].keys():
            if i==(len(downlink_infos)-1) or down_link_pair not in downlink_infos[i+1].keys():
                downlink_infos[i][down_link_pair][1] = i+1
            else:
                downlink_infos[i][down_link_pair][1] = downlink_infos[i+1][down_link_pair][1]
    for i,links_param in enumerate(links_params):
        start_ts,end_ts = downlink_infos[i][(0,links_param["topo"][0])]
        links_param["bw"][1] = get_bw(downlink_bw,start_ts,end_ts,i)
        for j in range(len(links_param["topo"])):
            if j%2==1:
                start_ts,end_ts = downlink_infos[i][(links_param["topo"][j],links_param["topo"][j+1])]
                links_param["bw"][j+2] = get_bw(downlink_bw,start_ts,end_ts,i)
    return links_params

def get_complete_relay_only_trace(    #set bw and loss
            origin_trace,   #only include rtt trace
            uplink_bw = 5,
            downlink_bw = 20,
            ground_link_bw = 20,
            uplink_loss = 0.1,
            downlink_loss = 0.1,
            ground_link_loss= 0,
            ground_link_rtt = 20,
            bw_fluctuation = False):
    max_midnode_num,total_midnode_num,isls,links_params = origin_trace
    for links_param in links_params:
        midnodes = len(links_param["topo"])
        sats = int((midnodes+1)/2)
        links_param["loss"] = [ground_link_loss]+[downlink_loss,uplink_loss]*sats+[ground_link_loss]
        links_param["bw"] = [ground_link_bw]+[downlink_bw,uplink_bw]*sats+[ground_link_bw]
        links_param["rtt"][0] = ground_link_rtt
        links_param["rtt"][-1] = ground_link_rtt
    if bw_fluctuation:
        links_params = add_bw_fluct_relay_only(links_params,downlink_bw)
    #links_params = links_params[141:]
    return  max_midnode_num,total_midnode_num,isls,links_params
# for test

def find_test_city():
    res = []
    for i in range(100):
        res.append((i,get_city_distance(6,i)))
        res = sorted(res,key=lambda x:x[1])
    for i in range(100):
        print(res[i])

def calc_average_hop(city1,city2):
    max_midnode_num,total_midnode_num,isls,links_params = get_trace(city1,city2,0,600)
    average_hop = np.mean([len(lp["topo"]) for lp in links_params])
    print(average_hop+3)
    return average_hop+3

'''
#max_midnode_num,total_midnode_num,isls,links_params = get_complete_trace(get_trace(6,9,0,600,route_algorithm="with_isl"),bw_fluctuation=True)
origin_trace = get_trace(6,2,0,600)
max_midnode_num,total_midnode_num,isls,links_params = get_complete_trace(origin_trace,uplink_bw=10,bw_fluctuation=True,ground_link_rtt=10)
#ax_midnode_num,total_midnode_num,isls,links_params = origin_trace
#uplink_bws = [links_param["bw"][-2] for links_param in links_params]
#print(uplink_bws)
#plt.plot([i for i in range(len(uplink_bws))],uplink_bws)
#plt.show()

print(" > max_midnode_num:",max_midnode_num)
print(" > total_midnode_num:",total_midnode_num)
print(" > isls:",len(isls),isls)
print(" > links_params:",len(links_params))
for i in range(len(links_params)):  #len(links_params)
    #if i==0 or links_params[i]["topo"]!=links_params[i-1]["topo"]:
        print("     > time:",i)
        print("     > topo:",links_params[i]["topo"])
        print("     > rtt:",links_params[i]["rtt"])
        print("     > loss:",links_params[i]["loss"])
        print("     > bw:",links_params[i]["bw"])
        print("")
'''

