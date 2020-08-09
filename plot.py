import argparse
from matplotlib import pyplot as plt
from helper_func import *

parser = argparse.ArgumentParser()
parser.add_argument('client_csv')
parser.add_argument('--server-csv', '-s')
parser.add_argument('--timestamp-align', '-t')
parser.add_argument('--no-detail-box', action='store_true')
args = parser.parse_args()

try:
    trace_id = int(args.client_csv)
    args.client_csv = f'../result_bbr/{trace_id}c.csv'
    args.server_csv = f'../result_bbr/{trace_id}s.csv'
except ValueError:
    pass

# timestamp_delta = -0.037

class WindowGoodput:
    def finalize(self, smooth_factor):
        for i in range(len(self.points)):
            self.points[i][1] /= self.window
        if smooth_factor == 1:
            return
        for i in range(1, len(self.points)):
            self.points[i][1] = (1 - smooth_factor) * self.points[i - 1][1] \
                            + smooth_factor * self.points[i][1]

    def plot(self):
        x = list(map(lambda x: x[0], self.points))
        y = list(map(lambda x: x[1], self.points))
        plt.plot(x, y)
        return plt.scatter(x, y)

class SlidingWindowGoodput(WindowGoodput):
    def __init__(self, window):
        self.window = window
        self.points = []
        self.data_in_window = []
        self.data_size = 0

    def append(self, time, size):
        self.data_in_window += [[time, size]]
        self.data_size += size
        while self.data_in_window[0][0] + self.window <= time:
            self.data_size -= self.data_in_window[0][1]
            self.data_in_window = self.data_in_window[1:]
        self.points += [[time, self.data_size]]

    def finalize(self):
        super().finalize(1)

class ConsecutiveWindowGoodput(WindowGoodput):
    def __init__(self, window):
        self.window = window
        self.points = []

    def append(self, time, size):
        if not self.points:
            self.points += [[time, size]]
            return
        while self.points[-1][0] + self.window <= time:
            self.points += [[self.points[-1][0] + self.window, 0]]
        self.points[-1][1] += size

    def finalize(self, factor):
        for i in range(len(self.points)):
            self.points[i][0] += self.window
        super().finalize(factor)

client_records, client_data_records, client_ack_records = read_packets(args.client_csv)

bandwidth_radio = ConsecutiveWindowGoodput(0.01)
bandwidth_client = SlidingWindowGoodput(0.25)

time_base = None

for pkt in client_data_records:
    size = int(pkt['tcp.len'])
    time = float(pkt['timestamp'])

    if time_base is None:
        time_base = time
    time -= time_base

    bandwidth_radio.append(time, size)
    bandwidth_client.append(time, size)

bandwidth_radio.finalize(0.125)
bandwidth_client.finalize()

if args.server_csv:
    server_records, server_data_records, server_ack_records = read_packets(args.server_csv)

if args.server_csv and not args.timestamp_align:
    timestamp_delta_min = float('-inf')
    timestamp_delta_max = float('+inf')

    j = 0
    for pkt in server_ack_records:
        while j > 0 and not packet_check_equal(client_ack_records[j], pkt) and \
                int(pkt['tcp.options.timestamp.tsval']) <= int(client_ack_records[j]['tcp.options.timestamp.tsval']):
            j -= 1
        while j < len(client_ack_records) - 1 and not packet_check_equal(client_ack_records[j], pkt) and \
                int(pkt['tcp.options.timestamp.tsval']) >= int(client_ack_records[j]['tcp.options.timestamp.tsval']):
            j += 1
        orig_pkt = client_ack_records[j]
        if not packet_check_equal(orig_pkt, pkt):
            continue

        timestamp_delta_min = max(timestamp_delta_min, float(orig_pkt['timestamp']) - float(pkt['timestamp']))

    j = 0
    for pkt in client_data_records:
        while j > 0 and not packet_check_equal(server_data_records[j], pkt) and \
                int(pkt['tcp.options.timestamp.tsval']) <= int(server_data_records[j]['tcp.options.timestamp.tsval']):
            j -= 1
        while j < len(server_data_records) - 1 and not packet_check_equal(server_data_records[j], pkt) and \
                int(pkt['tcp.options.timestamp.tsval']) >= int(server_data_records[j]['tcp.options.timestamp.tsval']):
            j += 1
        orig_pkt = server_data_records[j]
        if not packet_check_equal(orig_pkt, pkt):
            continue

        timestamp_delta_max = min(timestamp_delta_max, float(pkt['timestamp']) - float(orig_pkt['timestamp']))

    args.timestamp_align = (timestamp_delta_min + timestamp_delta_max) / 2
    print(f'INFO: Select {args.timestamp_align} as timestamp_align ' +
            f'from the interval [{timestamp_delta_min}, {timestamp_delta_max}]')
elif args.timestamp_align:
    args.timestamp_align = float(args.timestamp_align)

if args.server_csv:
    bandwidth_server_data = SlidingWindowGoodput(0.25)
    bandwidth_server_ack = SlidingWindowGoodput(0.25)

    for pkt in server_data_records:
        size = int(pkt['tcp.len'])
        time = float(pkt['timestamp']) - time_base
        bandwidth_server_data.append(time + args.timestamp_align, size)

    last_ack = None
    idx = 0
    for pkt in server_ack_records:
        ack = int(pkt['tcp.ack'])
        if ack == 0:
            continue
        if last_ack is None:
            last_ack = ack
        if ack <= last_ack:
            pkt.pop('ack_id')
            continue

        size = ack - last_ack
        time = float(pkt['timestamp']) - time_base
        bandwidth_server_ack.append(time + args.timestamp_align, size)
        pkt['ack_id'] = idx
        last_ack = ack
        idx += 1

    bandwidth_server_data.finalize()
    bandwidth_server_ack.finalize()

fig, ax = plt.subplots()
annot = ax.annotate("", xy=(0, 0),
        bbox=dict(boxstyle="round", fc="w"), arrowprops=dict(arrowstyle="->"),
        textcoords="offset points", xytext=(20, 20))
annot.set_visible(False)

bandwidth_radio.plot()
sc_client = bandwidth_client.plot()
if args.server_csv:
    sc_server_data = bandwidth_server_data.plot()
    sc_server_ack = bandwidth_server_ack.plot()

new_lines = []

def draw_new_line(point1, point2):
    global new_lines
    x = [point1[0], point2[0]]
    y = [point1[1], point2[1]]
    new_lines += plt.plot(x, y, '-.k')

def clean_new_lines():
    global new_lines
    for line in new_lines:
        line.remove()
    new_lines = []

def packet_text_to_disply(client_data_pkt):
    error_str = f"Client Packet No. {client_data_pkt['_ws.col.No.']}\n"

    client_ack_pkt = packet_search(client_records, client_data_pkt['id'], packet_check_ack, client_data_pkt)
    if client_ack_pkt is None:
        error_str += "ERROR: Cannot find the corresponding ACK packet."
        return error_str

    server_data_pkt = packet_search(server_records, 0, packet_check_equal, client_data_pkt)
    if server_data_pkt is not None:
        server_ack_pkt = packet_search(server_records, server_data_pkt['id'], packet_check_equal, client_ack_pkt)
    if server_data_pkt is None or server_ack_pkt is None:
        error_str += "ERROR: Cannot find the corresponding packets in server records."
        return error_str

    result_str = ""
    result_str += f"Server Data No. {server_data_pkt['_ws.col.No.']}\n"
    result_str += f"Client Data No. {client_data_pkt['_ws.col.No.']}\n"
    result_str += f"Client ACK No. {client_ack_pkt['_ws.col.No.']}\n"
    result_str += f"Server ACK No. {server_ack_pkt['_ws.col.No.']}\n"
    result_str += f"Server RTT: {server_ack_pkt['tcp.analysis.ack_rtt']}\n"
    result_str += f"Client ACK Delay: {float(client_ack_pkt['timestamp']) - float(client_data_pkt['timestamp'])}\n"
    result_str += "\n"

    server_last_pkt = server_data_pkt['data_id'] + 1
    while float(server_data_records[server_last_pkt]['timestamp']) + \
            args.timestamp_align <= float(client_ack_pkt['timestamp']):
        server_last_pkt += 1
    server_last_pkt = server_data_records[server_last_pkt - 1]
    result_str += "Bytes in fly: " + \
            f"{int(server_last_pkt['tcp.seq']) + int(server_last_pkt['tcp.len']) - int(client_ack_pkt['tcp.ack'])}"
    result_str += "\n\n"

    server_new_pkt = packet_search(server_records, server_ack_pkt['id'],
            lambda pkt: pkt['_ws.col.Destination'] == server_ack_pkt['_ws.col.Source'] and \
                    int(pkt['tcp.options.timestamp.tsecr']) >= int(server_ack_pkt['tcp.options.timestamp.tsval']))
    if server_new_pkt is not None:
        client_new_pkt = packet_search(client_records, client_ack_pkt['id'], packet_check_equal, server_new_pkt)
    if server_new_pkt is not None and client_new_pkt is not None:
        result_str += f"Server New No. {server_new_pkt['_ws.col.No.']}\n"
        result_str += f"Client New No. {client_new_pkt['_ws.col.No.']}\n"
        result_str += f"Client RTT: {float(client_new_pkt['timestamp']) - float(client_ack_pkt['timestamp'])}"
    else:
        result_str += "Failed to measure the client-side RTT."

    sid = server_data_pkt.get('data_id')
    cid = client_data_pkt.get('data_id')
    if sid is not None and cid is not None:
        draw_new_line(sc_client.get_offsets()[cid], sc_server_data.get_offsets()[sid])

    ack_id = server_ack_pkt.get('ack_id')
    if ack_id is not None and cid is not None:
        draw_new_line(sc_client.get_offsets()[cid], sc_server_ack.get_offsets()[ack_id])

    if server_new_pkt is not None and client_new_pkt is not None:
        sid = server_new_pkt.get('data_id')
        cid = client_new_pkt.get('data_id')
        if sid is not None and cid is not None:
            draw_new_line(sc_client.get_offsets()[cid], sc_server_data.get_offsets()[sid])

    return result_str

class MouseEventHandler:
    def onpress(self, event):
        self.moved = False

    def onmove(self, event):
        self.moved = True

    def onrelease(self, event):
        if self.moved or event.inaxes != ax:
            return
        clean_new_lines()

        ok, ind = sc_client.contains(event)
        if not ok:
            annot.set_visible(False)
            return

        ind = ind['ind'][0]
        annot.set_text(packet_text_to_disply(client_data_records[ind]))
        annot.xy = sc_client.get_offsets()[ind]
        if not args.no_detail_box:
            annot.set_visible(True)

if args.server_csv:
    handler = MouseEventHandler()
    fig.canvas.mpl_connect("button_press_event", handler.onpress)
    fig.canvas.mpl_connect("motion_notify_event", handler.onmove)
    fig.canvas.mpl_connect("button_release_event", handler.onrelease)

plt.show()
