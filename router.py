import sys
import socket
import threading
import time
import subprocess
import dv_pb2

INFINITY = 16

class Router:
    def __init__(self, router_name, tcp_port, udp_port, neighbors):
        self.router_name = router_name
        
        self.tcp_port = int(tcp_port)
        self.udp_port = int(udp_port)
        self.neighbors = neighbors 
        self.seq_no = 0

        print(f"[{time.strftime('%H:%M:%S')}] [Init] Router Started: Name='{self.router_name}'")

        # Edw apothikeuoume tous energous geitones (TCP connections, IPs, klp)
        self.active_neighbors = {}
        
        # O pinakas dromologhshs (Routing Table)
        self.routing_table = {}
        self.lock = threading.Lock()
        
        self.init_local_routes()
        
    def init_local_routes(self):
        try:
            # Diavazoume ta routes tou systhmatos (Linux kernel) gia na vroume ta topika diktya
            cmd = "ip route show"
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, _ = process.communicate()
            lines = output.decode('utf-8').split('\n')
            with self.lock:
                for line in lines:
                    parts = line.split()
                    if len(parts) > 0:
                        prefix = parts[0]
                        if '/' in prefix and 'default' not in prefix:
                            if prefix.startswith('172.17'): continue 
                            
                            # Prosthetoume ta topika diktya me metric 0
                            self.routing_table[prefix] = {
                                'next_hop': '-', 
                                'metric': 0,
                                'timestamp': time.time()
                            }
                            print(f"[{time.strftime('%H:%M:%S')}] [Routes] Added local network: {prefix}")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] [!] Error reading system routes: {e}")

    def install_route(self, prefix, next_hop_name):
        with self.lock:
            if next_hop_name not in self.active_neighbors:
                return
            next_hop_ip = self.active_neighbors[next_hop_name]['phys_ip']
        
        try:
            cmd = f"ip route replace {prefix} via {next_hop_ip}"
            subprocess.run(cmd, shell=True, check=True, stderr=subprocess.PIPE)
            print(f"[{time.strftime('%H:%M:%S')}] [Kernel] Installed: {prefix} via {next_hop_ip}")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] [!] Failed to install route {prefix}: {e}")

    def remove_route(self, prefix):
        try:
            cmd = f"ip route del {prefix}"
            subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL)
            print(f"[{time.strftime('%H:%M:%S')}] [Kernel] Removed: {prefix}")
        except:
            pass  # Το route μπορεί να μην υπάρχει ήδη

    def send_dv_updates(self, triggered=False):
        prefix_type = "TRIGGERED" if triggered else "PERIODIC"
        
        with self.lock:
            current_table = self.routing_table.copy()
            targets = []
            for name, info in self.active_neighbors.items():
                targets.append((name, info['phys_ip'], info['udp_port']))

            self.seq_no += 1
            curr_seq = self.seq_no

        for target_name, target_phys_ip, target_port in targets:
            msg = dv_pb2.DVMessage()
            msg.header.version = 1
            msg.header.router_id = self.router_name
            msg.header.seq = curr_seq
            msg.header.sent_at_ms = int(time.time() * 1000)
            
            count = 0
            for prefix, entry in current_table.items():
                r = msg.routes.add()
                r.prefix = prefix
                r.next_hop = entry['next_hop']
                
                # Efarmogi kanona "Split Horizon with Poison Reverse"
                # An mathame to route apo ton geitona pou tou stelnoume twra,
                # tou leme oti to kostos einai apeiro (16) gia na mhn to steilei pisw se emas.
                if entry['next_hop'] == target_name:
                    r.metric = INFINITY
                else:
                    r.metric = entry['metric']
                
                count += 1
            
            if count > 0:
                data = msg.SerializeToString()
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    sock.sendto(data, (target_phys_ip, int(target_port)))
                    if triggered: print(f"[{time.strftime('%H:%M:%S')}] [{prefix_type}] Sent update to {target_name} ({count} routes)")
                except: pass
                finally: sock.close()

    def periodic_dv_sender(self):
        # Stelnei to routing table kathe 20 deuterolepta se olous tous geitones
        UPDATE_INTERVAL = 20 
        print(f"[{time.strftime('%H:%M:%S')}] [System] Periodic DV Sender started ({UPDATE_INTERVAL}s)")
        while True:
            time.sleep(UPDATE_INTERVAL)
            with self.lock:
                now = time.time()
                # Ananewsh timestamp gia ta topika routes wste na mhn ta svhsei o garbage collector
                for prefix, entry in self.routing_table.items():
                    if entry['next_hop'] == '-':
                        entry['timestamp'] = now
            
            self.send_dv_updates(triggered=False)
            print(f"[{time.strftime('%H:%M:%S')}] [Periodic] Sent routing table update.")

    def cleanup_systems(self):
        print(f"[{time.strftime('%H:%M:%S')}] [System] Garbage Collector started")
        counter = 0
        while True:
            time.sleep(1)
            now = time.time()
            counter += 1

            if counter == 20:
                self.print_routing_table()
                counter = 0

            # 1. Elegxos gia "nekrous" geitones (TCP Keepalive timeout)
            dead_neighbors = []
            with self.lock:
                for name, info in self.active_neighbors.items():
                    # An exoume na lavoume Hello panw apo 15 sec, thewreitai dead
                    if now - info['last_hello'] > 15:
                        dead_neighbors.append(name)
            
            for name in dead_neighbors:
                print(f"[{time.strftime('%H:%M:%S')}] [Timeout] Neighbor {name} dead. Removing.")
                self.remove_neighbor(name)

            # 2. Elegxos gia lhgmena routes (Route Timeout)
            with self.lock:
                to_remove = []
                for prefix, entry in self.routing_table.items():
                    # An ena route den exei ananewthei gia 60 sec, diagrafetai
                    if entry['next_hop'] != '-' and (now - entry['timestamp'] > 60):
                        to_remove.append(prefix)
                
                for prefix in to_remove:
                    print(f"[{time.strftime('%H:%M:%S')}] [Timeout] Route {prefix} via {self.routing_table[prefix]['next_hop']} expired.")
                    del self.routing_table[prefix]
                    # Αφαιρούμε και από το kernel
                    self.remove_route(prefix)

    def start_udp_server(self):
        # Anoigei UDP socket gia na dexetai updates apo allous routers
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', self.udp_port))
        print(f"[{time.strftime('%H:%M:%S')}] [UDP] Listening on 0.0.0.0:{self.udp_port}")

        while True:
            try:
                data, _ = sock.recvfrom(4096)
                msg = dv_pb2.DVMessage()
                msg.ParseFromString(data)
                self.process_dv_update(msg.header.router_id, msg.routes, msg.header.seq)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] [!] UDP Error: {e}")

    def process_dv_update(self, sender_name, routes, seq_no):
        topology_changed = False
        with self.lock:
            if sender_name not in self.active_neighbors:
                return
            # Elegxos Sequence Number gia na aporripsoume palia paketa
            last_seq = self.active_neighbors[sender_name].get('last_seq', -1)
            if seq_no <= last_seq:
                return
            self.active_neighbors[sender_name]['last_seq'] = seq_no

            print(f"[{time.strftime('%H:%M:%S')}] [UDP-Recv] Update from {sender_name} (Seq: {seq_no})")

            for r in routes:
                dest = r.prefix
                # To neo kostos einai to kostos tou geitona + 1 (hop count)
                new_metric = min(r.metric + 1, INFINITY)
                
                # Eidhsh: To diktyo einai unreachable (Metric >= 16)
                if new_metric >= INFINITY:
                    if dest in self.routing_table and self.routing_table[dest]['next_hop'] == sender_name:
                        # An o torinos mas next-hop pei oti to route pethane,
                        # to markaroume ws INFINITY (Poison) alla den to svhnoume amesws
                        # gia na prolavoume na enhmerwsoume tous allous.
                        if self.routing_table[dest]['metric'] < INFINITY:
                            self.routing_table[dest]['metric'] = INFINITY
                            self.routing_table[dest]['timestamp'] = time.time() 
                            print(f"[{time.strftime('%H:%M:%S')}] [Route Dead] {dest} via {sender_name} became unreachable (Metric 16)")
                            topology_changed = True
                            # Αφαιρούμε το route από το kernel γιατί δεν είναι πλέον έγκυρο
                            self.remove_route(dest)
                    continue

                # Kanonikh logikh Distance Vector
                if dest not in self.routing_table:
                    # Neos proorismos pou den kserame
                    self.routing_table[dest] = {
                        'next_hop': sender_name, 
                        'metric': new_metric, 
                        'timestamp': time.time()
                    }
                    print(f"[{time.strftime('%H:%M:%S')}] [New Route] {dest} via {sender_name} (Cost {new_metric})")
                    topology_changed = True
                    # Εγκαθιστούμε το νέο route στο kernel
                    self.install_route(dest, sender_name)
                    
                else:
                    current = self.routing_table[dest]
                    
                    # Periptwsh A: Vrikame kalytero monopati (mikrotero metric)
                    if new_metric < current['metric']:
                        self.routing_table[dest] = {
                            'next_hop': sender_name, 
                            'metric': new_metric, 
                            'timestamp': time.time()
                        }
                        print(f"[{time.strftime('%H:%M:%S')}] [Better Path] {dest} via {sender_name} (Cost {new_metric})")
                        topology_changed = True
                        # Ενημερώνουμε το kernel με το καλύτερο μονοπάτι
                        self.install_route(dest, sender_name)
                        
                    # Periptwsh B: O router pou hdh xrhsimopoioume allakse to kostos tou
                    # Prepei na enimerwsoume to diko mas table, akoma kai an to kostos megalwse.
                    elif current['next_hop'] == sender_name:
                        current['timestamp'] = time.time()
                        if new_metric != current['metric']:
                            current['metric'] = new_metric
                            print(f"[{time.strftime('%H:%M:%S')}] [Route Adj] {dest} metric changed to {new_metric} via {sender_name}")
                            topology_changed = True

        # An allakse kati ston pinaka, stelnoume amesws updates (Triggered Update)
        if topology_changed:
            threading.Thread(target=self.send_dv_updates, args=(True,)).start()

    def send_periodic_hellos(self):
        # Stelnei mikra TCP paketa "Hello" gia na diatirei th syndesh
        while True:
            time.sleep(5)
            msg = dv_pb2.HelloMessage()
            msg.header.router_id = self.router_name 
            data = msg.SerializeToString() 
            
            with self.lock:
                neighbors = list(self.active_neighbors.items())
            
            for name, info in neighbors:
                try: 
                    info['tcp_conn'].sendall(data)
                    print(f"[{time.strftime('%H:%M:%S')}] [Hello] Sent to {name}")
                except: self.remove_neighbor(name)

    def remove_neighbor(self, name):
        with self.lock:
            if name in self.active_neighbors:
                try: self.active_neighbors[name]['tcp_conn'].close()
                except: pass
                del self.active_neighbors[name]
                
                # Otan enas geitonas "pethainei", den svhnoume ta routes tou amesws.
                # Ta "dhlitiriazoume" (Poison) thetontas metric = 16.
                # Auto ginetai gia na mathei to ypoloipo diktyo oti ta routes pethanan.
                poisoned_count = 0
                routes_to_remove = []
                for prefix, entry in self.routing_table.items():
                    if entry['next_hop'] == name:
                        entry['metric'] = INFINITY
                        entry['timestamp'] = time.time() 
                        poisoned_count += 1
                        routes_to_remove.append(prefix)
                
                # Αφαιρούμε τα routes από το kernel (έξω από το lock)
                for prefix in routes_to_remove:
                    self.remove_route(prefix)
                
                print(f"[{time.strftime('%H:%M:%S')}] [Cleanup] Poisoned {poisoned_count} routes via {name}")
        
        # Triggered update gia na pame ta asxhma nea stous allous
        threading.Thread(target=self.send_dv_updates, args=(True,)).start()

    def handle_connection(self, conn, addr, initiated):
        neighbor_name = None
        try:
            # Handshake: Antallagh onomatwn kai UDP ports me ton geitona
            my = dv_pb2.ConnParamMessage()
            my.header.router_id = self.router_name; my.port = self.udp_port
            
            if initiated:
                conn.sendall(my.SerializeToString())
                data = conn.recv(1024)
                if not data: return
                other = dv_pb2.ConnParamMessage(); other.ParseFromString(data)
            else:
                data = conn.recv(1024) 
                if not data: return
                other = dv_pb2.ConnParamMessage(); other.ParseFromString(data)
                conn.sendall(my.SerializeToString())

            neighbor_name = other.header.router_id
            real_ip = addr[0]
            print(f"[{time.strftime('%H:%M:%S')}] [Connected] {neighbor_name} (IP: {real_ip})")
            
            with self.lock:
                self.active_neighbors[neighbor_name] = {
                    'tcp_conn': conn, 
                    'udp_port': other.port, 
                    'phys_ip': real_ip,
                    'last_hello': time.time(),
                    'last_seq' : -1
                }
            
            # Molus syndethoume, stelnoume olo to routing table
            self.send_dv_updates(triggered=True)

            # Loop pou akouei gia Hello messages
            while True:
                data = conn.recv(1024)
                if not data: break
                try: 
                    h = dv_pb2.HelloMessage()
                    h.ParseFromString(data)
                    with self.lock:
                        if neighbor_name in self.active_neighbors:
                            self.active_neighbors[neighbor_name]['last_hello'] = time.time()
                            print(f"[{time.strftime('%H:%M:%S')}] [Hello] Received from {neighbor_name}")
                except: pass
        except: pass
        finally:
            conn.close()
            if neighbor_name: self.remove_neighbor(neighbor_name)

    def start_tcp_server(self):
        # TCP server gia thn arxikh syndesh twn geitonwn
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('0.0.0.0', self.tcp_port))
            s.listen(5)
            while True:
                c, a = s.accept()
                threading.Thread(target=self.handle_connection, args=(c, a, False), daemon=True).start()
        except Exception as e: print(f"[{time.strftime('%H:%M:%S')}] [Server Error] {e}")

    def connect_neighbors(self):
        time.sleep(2)
        # Prospathoume na syndethoume energitika stous geitones pou dothikan sthn eisodo
        for nip, nport in self.neighbors:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((nip, int(nport)))
                threading.Thread(target=self.handle_connection, args=(s, (nip, nport), True), daemon=True).start()
            except: print(f"[{time.strftime('%H:%M:%S')}] [Fail] Connect to {nip}")

    def run(self):
        # Ekkini ola ta threads
        threading.Thread(target=self.start_tcp_server, daemon=True).start()
        threading.Thread(target=self.start_udp_server, daemon=True).start()
        threading.Thread(target=self.periodic_dv_sender, daemon=True).start()
        threading.Thread(target=self.send_periodic_hellos, daemon=True).start()
        threading.Thread(target=self.cleanup_systems, daemon=True).start()
        self.connect_neighbors()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt: print(f"[{time.strftime('%H:%M:%S')}] Exit")

    def print_routing_table(self):
        print(f"\n[{time.strftime('%H:%M:%S')}] " + "=" * 60)
        print(f"[{time.strftime('%H:%M:%S')}] [Routing Table @ {self.router_name}]")
        print(f"[{time.strftime('%H:%M:%S')}] " + "=" * 60)

        if not self.routing_table:
            print(f"[{time.strftime('%H:%M:%S')}]    (Empty Routing Table)")
        else:
            sorted_routes = sorted(self.routing_table.items())
            
            for prefix, entry in sorted_routes:
                metric = entry['metric']
                next_hop = entry['next_hop']
                
                if metric >= INFINITY:
                    arrow = "[!]"             
                    status = " << DEAD >>"    
                    metric_str = f"{metric}"
                else:
                    arrow = "→  "
                    status = ""
                    metric_str = f"{metric}"

                print(f"[{time.strftime('%H:%M:%S')}] {arrow} {prefix:<18} next-hop: {next_hop:<10} metric: {metric_str:<3}{status}")
                entry["last_metric"] = metric

        print(f"[{time.strftime('%H:%M:%S')}] " + "-" * 60)
        print(f"[{time.strftime('%H:%M:%S')}] [Active Neighbors]")
        if not self.active_neighbors:
            print(f"[{time.strftime('%H:%M:%S')}]    (No Active Neighbors)")
        else:
            for name, info in self.active_neighbors.items():
                ago = time.time() - info["last_hello"]
                l_seq = info.get('last_seq', -1)
                print(f"[{time.strftime('%H:%M:%S')}] • {name:<10} IP: {info['phys_ip']:<15} lastSeq: {l_seq:<5} last_hello: {ago:.1f}s ago")
        print(f"[{time.strftime('%H:%M:%S')}] " + "=" * 60 + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(f"[{time.strftime('%H:%M:%S')}] Usage: python router.py <ROUTER_NAME> <tcp> <udp> [neighbor_ip:port ...]")
        sys.exit(1)
    
    name = sys.argv[1]
    tcp = sys.argv[2]
    udp = sys.argv[3]
    neighbors = [x.split(':') for x in sys.argv[4:]]
    
    Router(name, tcp, udp, neighbors).run()