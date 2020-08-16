import csv
import ctypes

PACKET_SERVER_DATA = 1
PACKET_CLIENT_DATA = 2
PACKET_CLIENT_ACK  = 3
PACKET_SERVER_ACK  = 4

class Packet:
    pass

def get_packets(client_records, server_records, tsdelta):
    endpoints = ((client_records[0]['_ws.col.Source'], \
                  client_records[0]['_ws.col.Destination']), \
                 (server_records[0]['_ws.col.Source'], \
                  server_records[0]['_ws.col.Destination']) \
                 if server_records else ('', ''))
    assert '1' == client_records[0].get('tcp.flags.syn', '1')
    assert '0' == client_records[0].get('tcp.flags.ack', '0')
    if server_records:
        assert '1' == server_records[0].get('tcp.flags.syn', '1')
        assert '0' == server_records[0].get('tcp.flags.ack', '0')

    tsbase = float(client_records[0]['timestamp'])
    client_records.append(dict(timestamp='inf'))
    server_records.append(dict(timestamp='inf'))

    def is_ack_record(record, is_server):
        if int(record.get('tcp.flags.syn', '0')):
            return -1
        client, server = endpoints[bool(is_server)]
        if record['_ws.col.Source'] == client and \
                record['_ws.col.Destination'] == server and \
                not int(record['tcp.len']):
            return 1
        if record['_ws.col.Source'] == server and \
                record['_ws.col.Destination'] == client and \
                int(record['tcp.len']):
            return 0
        return -1

    def fill_packet_info(record, packet, is_server, is_ack):
        packet.timestamp = float(record['timestamp']) - tsbase
        if is_server:
            packet.type = PACKET_SERVER_ACK if is_ack else PACKET_SERVER_DATA
            packet.timestamp += tsdelta
        else:
            packet.type = PACKET_CLIENT_ACK if is_ack else PACKET_CLIENT_DATA
        packet.no = int(record['_ws.col.No.'])
        packet.seq = int(record.get('tcp.seq', '0'))
        packet.ack = int(record.get('tcp.ack', '0'))
        packet.len = int(record['tcp.len'])
        packet.tsval = int(record.get('tcp.options.timestamp.tsval', '0'))
        packet.tsecr = int(record.get('tcp.options.timestamp.tsecr', '0'))
        packet.end_seq = ctypes.c_uint32(packet.seq + packet.len).value
        # FIXME: Some fields don't exist in UDP. Maybe a more elegant way
        #        to deal with them is needed here.

    packets = []
    i = j = 0
    while i < len(client_records) - 1 or j < len(server_records) - 1:
        if float(client_records[i]['timestamp']) <= \
                float(server_records[j]['timestamp']) + tsdelta:
            record = client_records[i]
            is_server = False
            i += 1
        else:
            record = server_records[j]
            is_server = True
            j += 1

        is_ack = is_ack_record(record, is_server)
        if is_ack < 0:
            continue

        packet = Packet()
        fill_packet_info(record, packet, is_server, is_ack)
        packet.idx = len(packets)
        packets.append(packet)

    return packets

def read_records(filename):
    titles = None
    client_addr = server_addr = None

    data_records = []
    ack_records = []
    records = []

    csv_file = open(filename, 'r')
    csv_reader = csv.reader(csv_file)

    for row in csv_reader:
        if titles is None:
            titles = row
            if titles.count('timestamp') == 0:
                titles[titles.index('_ws.col.Time')] = 'timestamp'
            if titles.count('udp.length') > 0:
                titles[titles.index('udp.length')] = 'tcp.len'
            continue

        row = dict(zip(titles, row))
        if client_addr is None:
            client_addr = row['_ws.col.Source']
        if server_addr is None:
            server_addr = row['_ws.col.Destination']

        records.append(row)
        if row['_ws.col.Source'] == client_addr and \
                not int(row['tcp.len']):
            ack_records.append(row)
        if row['_ws.col.Source'] == server_addr and \
                int(row['tcp.len']):
            data_records.append(row)

        if len(records) >= 100000:
            break

    csv_file.close()
    return records, data_records, ack_records

def packet_check_equal(pkt1, pkt2):
    if pkt1['tcp.ack'] != pkt2['tcp.ack'] or \
            pkt1['tcp.options.timestamp.tsval'] != pkt2['tcp.options.timestamp.tsval']:
        return False
    if bool(int(pkt1['tcp.len'])) ^ bool(int(pkt2['tcp.len'])):
        return False
    return int(pkt2['tcp.seq']) >= int(pkt1['tcp.seq']) and \
            int(pkt2['tcp.seq']) < int(pkt1['tcp.seq']) + max(1, int(pkt1['tcp.len']))

def packet_check_ack(data_pkt, ack_pkt):
    return int(ack_pkt['tcp.ack']) >= int(data_pkt['tcp.len']) + int(data_pkt['tcp.seq']) and \
            data_pkt['_ws.col.Source'] == ack_pkt['_ws.col.Destination'] and \
            data_pkt['_ws.col.Destination'] == ack_pkt['_ws.col.Source']
