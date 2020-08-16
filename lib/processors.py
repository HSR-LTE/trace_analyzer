from matplotlib import pyplot as plt
from lib.packets import *
from lib.int32 import *

class PacketProcessor:
    def on_server_data(self, pkt):
        pass
    def on_client_data(self, pkt):
        pass
    def on_client_ack(self, pkt):
        pass
    def on_server_ack(self, pkt):
        pass

    def handle_server_data(self, pkt):
        return self.on_server_data(pkt)
    def handle_client_data(self, pkt):
        return self.on_client_data(pkt)
    def handle_client_ack(self, pkt):
        return self.on_client_ack(pkt)
    def handle_server_ack(self, pkt):
        return self.on_server_ack(pkt)

    def process(self, packets):
        for pkt in packets:
            if pkt.type == PACKET_SERVER_DATA:
                self.handle_server_data(pkt)
            elif pkt.type == PACKET_CLIENT_DATA:
                self.handle_client_data(pkt)
            elif pkt.type == PACKET_CLIENT_ACK:
                self.handle_client_ack(pkt)
            elif pkt.type == PACKET_SERVER_ACK:
                self.handle_server_ack(pkt)
            else:
                raise ValueError("The packet type is invalid.")

class ClientServerMatcher(PacketProcessor):
    def __init__(self):
        super().__init__()

        self.server_tsval_dict = {}
        self.client_tsval_dict = {}
        self.seq_dict = {}
        self.rcv_una_packets = []

    def on_server_data(self, packet):
        if not self.server_tsval_dict.get(packet.tsval):
            self.server_tsval_dict[packet.tsval] = []
        self.server_tsval_dict[packet.tsval].append(packet)
        packet.pair_pkt = None

        if not self.seq_dict.get(packet.seq):
            self.seq_dict[packet.seq] = []
            packet.retrans = None
        else:
            packet.retrans = self.seq_dict[packet.seq][-1]
        self.seq_dict[packet.seq].append(packet)

    def on_client_data(self, packet):
        packet.pair_pkt = None
        for pkt in self.server_tsval_dict.get(packet.tsval, []):
            if not after(pkt.seq, packet.seq) and \
                    after(pkt.end_seq, packet.seq):
                packet.pair_pkt = pkt
                pkt.pair_pkt = packet
                break

        packet.ack_pkt = None
        self.rcv_una_packets.append(packet)

    def on_client_ack(self, packet):
        new_list = []
        for pkt in self.rcv_una_packets:
            if not before(packet.ack, pkt.end_seq):
                pkt.ack_pkt = packet
            else:
                new_list.append(pkt)
        self.rcv_una_packets = new_list

        if not self.client_tsval_dict.get(packet.tsval):
            self.client_tsval_dict[packet.tsval] = []
        self.client_tsval_dict[packet.tsval].append(packet)
        packet.pair_pkt = None

    def on_server_ack(self, packet):
        packet.pair_pkt = None
        for pkt in self.client_tsval_dict.get(packet.tsval, []):
            if packet.ack == pkt.ack:
                pkt.pair_pkt = packet
                packet.pair_pkt = pkt
                break

class ClientPlotter(PacketProcessor):
    def __init__(self):
        super().__init__()

        self.curve_x = []
        self.curve_y = []
        self.curve_packets = []

        self.snd_nxt = 0
        self.rcv_nxt = 0
        self.bytes_received = 0

        self.history = dict()

    def handle_client_data(self, packet):
        if not self.rcv_nxt or after(packet.end_seq, self.rcv_nxt):
            self.rcv_nxt = packet.end_seq # TODO: disordered packet
        self.bytes_received += packet.len

        val = super().handle_client_data(packet)

        packet.curve_id = len(self.curve_packets)
        self.curve_packets.append(packet)
        self.curve_x.append(packet.timestamp)
        self.curve_y.append(val)

    def handle_client_ack(self, packet):
        if self.history.get(packet.tsval) is None:
            self.history[packet.tsval] = dict(snd_nxt=self.snd_nxt, \
                    rcv_nxt=self.rcv_nxt, bytes_received=self.bytes_received, \
                    time=packet.timestamp)

        super().handle_client_ack(packet)

    def handle_server_data(self, packet):
        if not self.snd_nxt or after(packet.end_seq, self.snd_nxt):
            self.snd_nxt = packet.end_seq

        super().handle_server_data(packet)

    def plot(self):
        plt.plot(self.curve_x, self.curve_y)
        return (plt.scatter(self.curve_x, self.curve_y), )

class ServerPlotter(PacketProcessor):
    def __init__(self, merged_plot=False):
        super().__init__()

        self.data_curve_x = []
        self.data_curve_y = []
        self.data_curve_packets = []
        self.ack_curve_x = []
        self.ack_curve_y = []
        self.ack_curve_packets = []
        self.merged_plot = merged_plot
        if self.merged_plot:
            self.curve_x = []
            self.curve_y = []

        self.snd_nxt = 0
        self.snd_una = 0
        self.delivered = 0
        self.bytes_acked = 0

        self.history = dict()

    def handle_server_data(self, packet):
        if not self.snd_nxt or after(packet.end_seq, self.snd_nxt):
            self.snd_nxt = packet.end_seq
        self.delivered += packet.len

        if self.history.get(packet.tsval) is None:
            self.history[packet.tsval] = dict(snd_nxt=self.snd_nxt, \
                    snd_una=self.snd_una, delivered=self.delivered, \
                    bytes_acked=self.bytes_acked, time=packet.timestamp)

        val = super().handle_server_data(packet)

        packet.curve_id = len(self.data_curve_packets)
        self.data_curve_packets.append(packet)
        self.data_curve_x.append(packet.timestamp)
        self.data_curve_y.append(val)
        if self.merged_plot:
            self.curve_x.append(packet.timestamp)
            self.curve_y.append(val)

    def handle_server_ack(self, packet):
        newly_acked = 0
        if not self.snd_una or after(packet.ack, self.snd_una):
            newly_acked = minus(packet.ack, self.snd_una)
            self.bytes_acked += newly_acked
            if not self.snd_una:
                newly_acked = 0
            self.snd_una = packet.ack # TODO: SACK

        self.newly_acked = newly_acked
        val = super().handle_server_ack(packet)
        del self.newly_acked

        packet.curve_id = len(self.ack_curve_packets)
        self.ack_curve_packets.append(packet)
        self.ack_curve_x.append(packet.timestamp)
        self.ack_curve_y.append(val)
        if self.merged_plot:
            self.curve_x.append(packet.timestamp)
            self.curve_y.append(val)

    def plot(self):
        if self.merged_plot:
            plt.plot(self.curve_x, self.curve_y)
        else:
            plt.plot(self.data_curve_x, self.data_curve_y)
            plt.plot(self.ack_curve_x, self.ack_curve_y)
        sc1 = plt.scatter(self.data_curve_x, self.data_curve_y)
        sc2 = plt.scatter(self.ack_curve_x, self.ack_curve_y)
        return (sc1, sc2)

class ClientBifPlotter(ClientPlotter):
    def on_client_data(self, packet):
        if self.snd_nxt and self.rcv_nxt:
            return minus(self.snd_nxt, self.rcv_nxt) # TODO: holes
        return 0

class ServerBifPlotter(ServerPlotter):
    def on_server_data(self, packet):
        if self.snd_nxt and self.snd_una:
            return minus(self.snd_nxt, self.snd_una)
        return 0

    def on_server_ack(self, packet):
        if self.snd_nxt and self.snd_una:
            return minus(self.snd_nxt, self.snd_una)
        return 0

class ClientRttPlotter(ClientPlotter):
    def on_client_data(self, packet):
        old = self.history.get(packet.tsecr)
        if old is None:
            return -1
        return packet.timestamp - old['time']

class ServerRttPlotter(ServerPlotter):
    def __init__(self):
        super().__init__()
        self.srtt = 0

    def on_server_ack(self, packet):
        old = self.history.get(packet.tsecr)
        if old is None:
            return -1

        rtt = packet.timestamp - old['time']
        if not self.srtt:
            self.srtt = rtt
            self.mdev = rtt / 2
            self.rttvar = max(self.mdev, 0.2)
            self.mdev_max = self.rttvar
            self.rtt_seq = self.snd_nxt
        else:
            m = rtt - self.srtt
            self.srtt += m / 8
            if m < 0:
                m = -m
                m -= self.mdev
                if m > 0:
                    m /= 8
            else:
                m -= self.mdev
            self.mdev += m / 4
            if self.mdev > self.mdev_max:
                self.mdev_max = self.mdev
                if self.mdev_max > self.rttvar:
                    self.rttvar = self.mdev_max
            if after(self.snd_una, self.rtt_seq):
                if self.mdev_max < self.rttvar:
                    self.rttvar -= (self.rttvar - self.mdev_max) / 4
                self.rtt_seq = self.snd_nxt
                self.mdev_max = 0.2

        return rtt

    def on_server_data(self, packet):
        if not self.srtt:
            return -1
        return self.srtt + self.rttvar * 4

class ClientBwPlotter(ClientPlotter):
    def on_client_data(self, packet):
        old = self.history.get(packet.tsecr)
        if old is None:
            return -1

        size = self.bytes_received - old['bytes_received']
        time = packet.timestamp - old['time']
        return size / time

class ServerBwPlotter(ServerPlotter):
    def __init__(self):
        super().__init__()
        self.last_tsecr = 0

    def on_server_data(self, packet):
        if not self.last_tsecr:
            return -1
        old = self.history[self.last_tsecr]

        size = self.delivered - old['delivered']
        time = packet.timestamp - old['time']
        return size / time

    def on_server_ack(self, packet):
        old = self.history.get(packet.tsecr)
        if old is None:
            return -1
        if not self.last_tsecr or after(packet.tsecr, self.last_tsecr):
            self.last_tsecr = packet.tsecr

        size = self.bytes_acked - old['bytes_acked']
        time = packet.timestamp - old['time']
        return size / time

class WindowMeasure:
    def __init__(self, win_size):
        self.window = []
        self.sum = 0
        self.win_size = win_size

    def append(self, time, data):
        self.window.append((time, data))
        self.sum += data
        i = 0
        while self.window[i][0] <= time - self.win_size:
            self.sum -= self.window[i][1]
            i += 1
        self.window = self.window[i:]
        return self.sum

class ClientWinBwPlotter(ClientPlotter):
    def __init__(self, win=0.25):
        super().__init__()
        self.win = WindowMeasure(win)
        self.win_size = win

    def on_client_data(self, packet):
        sz = self.win.append(packet.timestamp, packet.len)
        return sz / self.win_size

class ServerWinBwPlotter(ServerPlotter):
    def __init__(self, win=0.25):
        super().__init__()
        self.data_win = WindowMeasure(win)
        self.ack_win = WindowMeasure(win)
        self.win_size = win

    def on_server_data(self, packet):
        sz = self.data_win.append(packet.timestamp, packet.len)
        return sz / self.win_size

    def on_server_ack(self, packet):
        sz = self.ack_win.append(packet.timestamp, self.newly_acked)
        return sz / self.win_size
