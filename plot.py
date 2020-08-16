import argparse
from matplotlib import pyplot as plt
from lib.packets import *
from lib.processors import *

parser = argparse.ArgumentParser()
parser.add_argument('client_csv')
parser.add_argument('--plotter', '-p', choices=['rtt', 'bw', 'bif', 'win-bw'], required=True)
parser.add_argument('--server-csv', '-s')
parser.add_argument('--timestamp-align', '-t')
parser.add_argument('--no-detail-box', action='store_true')
parser.add_argument('--highlight-retransmission', action='store_true')
args = parser.parse_args()

try:
    trace_id = int(args.client_csv)
    args.client_csv = f'../result_bbr/{trace_id}c.csv'
    args.server_csv = f'../result_bbr/{trace_id}s.csv'
except ValueError:
    pass

plotter_dict = {'rtt'    : (ClientRttPlotter,   ServerRttPlotter,   ), \
                'bw'     : (ClientBwPlotter,    ServerBwPlotter,    ), \
                'bif'    : (ClientBifPlotter,   ServerBifPlotter,   ), \
                'win-bw' : (ClientWinBwPlotter, ServerWinBwPlotter, ), }

client_records, client_data_records, client_ack_records = read_records(args.client_csv)

server_records = []
if args.server_csv:
    server_records, server_data_records, server_ack_records = read_records(args.server_csv)

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
else:
    args.timestamp_align = 0

packets = get_packets(client_records, server_records, args.timestamp_align)
ClientServerMatcher().process(packets)

client_plotter, server_plotter = plotter_dict[args.plotter]
client_plotter = client_plotter()
server_plotter = server_plotter()
client_plotter.process(packets)
server_plotter.process(packets)

fig, ax = plt.subplots()
annot = ax.annotate("", xy=(0, 0),
        bbox=dict(boxstyle="round", fc="w"), arrowprops=dict(arrowstyle="->"),
        textcoords="offset points", xytext=(20, 20))
annot.set_visible(False)

sc_client, = client_plotter.plot()
sc_server_data, sc_server_ack = server_plotter.plot()

new_lines = []

def draw_new_line(point1, point2, fmt='-.k', **kwargs):
    global new_lines
    x = [point1[0], point2[0]]
    y = [point1[1], point2[1]]
    new_lines += plt.plot(x, y, fmt, **kwargs)

def clean_new_lines():
    global new_lines
    for line in new_lines:
        line.remove()
    new_lines = []

if args.highlight_retransmission and args.server_csv:
    for pkt in packets:
        if pkt.type != PACKET_SERVER_DATA:
            continue
        if pkt.retrans is None:
            continue
        offsets = sc_server_data.get_offsets()
        draw_new_line(offsets[pkt.curve_id], \
                offsets[pkt.retrans.curve_id], '#808080', alpha=0.3)
    new_lines = []

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
        if ok:
            ind = ind['ind'][0]
            client_data_pkt = client_plotter.curve_packets[ind]
            server_data_pkt = getattr(client_data_pkt, 'pair_pkt', None)
            self.draw_information(client_data_pkt, server_data_pkt)

            annot.xy = sc_client.get_offsets()[ind]
            annot.set_visible(not args.no_detail_box)
            return

        ok, ind = sc_server_data.contains(event)
        if ok:
            ind = ind['ind'][0]
            server_data_pkt = server_plotter.data_curve_packets[ind]
            client_data_pkt = getattr(server_data_pkt, 'pair_pkt', None)
            self.draw_information(client_data_pkt, server_data_pkt)

            annot.xy = sc_server_data.get_offsets()[ind]
            annot.set_visible(not args.no_detail_box)
            return

        annot.set_visible(False)
        return

    def draw_information(self, client_data_pkt, server_data_pkt):
        client_ack_pkt = getattr(client_data_pkt, 'ack_pkt', None)
        server_ack_pkt = getattr(client_ack_pkt, 'pair_pkt', None)

        result_str = f"Server Data No. {getattr(server_data_pkt, 'no', None)}\n"
        if server_data_pkt is not None:
            result_str += f"SEQ: {server_data_pkt.seq}\n"
            result_str += f"LEN: {server_data_pkt.len}\n"
        result_str += "\n"

        result_str += f"Client Data No. {getattr(client_data_pkt, 'no', None)}\n"
        if client_data_pkt is not None:
            result_str += f"SEQ: {client_data_pkt.seq}\n"
            result_str += f"LEN: {client_data_pkt.len}\n"
        result_str += "\n"

        result_str += f"Client ACK No. {getattr(client_ack_pkt, 'no', None)}\n"
        result_str += f"Server ACK No. {getattr(server_ack_pkt, 'no', None)}\n"
        if client_ack_pkt is not None:
            result_str += f"ACK: {client_ack_pkt.ack}\n"

        if client_data_pkt is not None and server_data_pkt is not None:
            draw_new_line(sc_client.get_offsets()[client_data_pkt.curve_id], \
                    sc_server_data.get_offsets()[server_data_pkt.curve_id])
        if client_data_pkt is not None and server_ack_pkt is not None:
            draw_new_line(sc_client.get_offsets()[client_data_pkt.curve_id], \
                    sc_server_ack.get_offsets()[server_ack_pkt.curve_id])

        annot.set_text(result_str[:-1])

handler = MouseEventHandler()
fig.canvas.mpl_connect("button_press_event", handler.onpress)
fig.canvas.mpl_connect("motion_notify_event", handler.onmove)
fig.canvas.mpl_connect("button_release_event", handler.onrelease)

plt.show()
