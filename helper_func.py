import csv

def read_packets(filename):
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
            continue

        row = dict(zip(titles, row))
        if client_addr is None:
            client_addr = row['_ws.col.Source']
        if server_addr is None:
            server_addr = row['_ws.col.Destination']

        records.append(row)
        row['id'] = len(records) - 1
        if row['_ws.col.Source'] == client_addr and \
                not int(row['tcp.len']):
            ack_records.append(row)
            row['ack_id'] = len(ack_records) - 1
        if row['_ws.col.Source'] == server_addr and \
                int(row['tcp.len']):
            data_records.append(row)
            row['data_id'] = len(data_records) - 1

    csv_file.close()
    return records, data_records, ack_records


def packet_check_equal(pkt1, pkt2):
    return pkt1['tcp.seq'] == pkt2['tcp.seq'] and \
            pkt1['tcp.ack'] == pkt2['tcp.ack'] and \
            pkt1['tcp.len'] == pkt2['tcp.len'] and \
            pkt1['tcp.options.timestamp.tsval'] == pkt2['tcp.options.timestamp.tsval'] and \
            pkt1['tcp.options.timestamp.tsecr'] == pkt2['tcp.options.timestamp.tsecr']

def packet_check_ack(data_pkt, ack_pkt):
    return int(ack_pkt['tcp.ack']) >= int(data_pkt['tcp.len']) + int(data_pkt['tcp.seq']) and \
            data_pkt['_ws.col.Source'] == ack_pkt['_ws.col.Destination'] and \
            data_pkt['_ws.col.Destination'] == ack_pkt['_ws.col.Source']

def packet_search(records, idx, func, *args):
    idx = next(filter(lambda i: func(*args, records[i]), range(idx, len(records))), None)
    if idx is None:
        return None
    return records[idx]
