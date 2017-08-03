import dockercmd
import bitcoincmd
import config
import bash
from bitcoinrpc.authproxy import AuthServiceProxy
import logging
import tccmd
import proxycmd
import utils


class Node:
    def __init__(self, name, ip):
        self.name = name
        self.ip = ip

    def rm(self):
        return bash.check_output(dockercmd.rm_container(self.name))

    def rm_silent(self):
        return bash.call_silent(dockercmd.rm_container(self.name))


class PublicNode:
    def __init__(self, latency):
        self.latency = latency
        self.outgoing_ips = []


class BitcoinNode(Node):
    log_file = config.client_dir + '/debug.log'

    def __init__(self, name, ip):
        super().__init__(name, ip)
        self.name = name
        self.ip = ip
        self.spent_to_address = ''
        self.rpc_connection = None

    def run(self):
        bash.check_output(bitcoincmd.start(self))
        self.rpc_connection = AuthServiceProxy(config.create_rpc_connection_string(self.ip))

    def delete_peers_file(self):
        return bash.check_output(bitcoincmd.rm_peers(self.name))

    def execute_rpc(self,  *args):
        method_to_call = getattr(self.rpc_connection, args[0])

        logging.info('{} {}'.format(self.name, args))
        return_value = method_to_call(*args[1:])
        logging.info(return_value)

        return return_value

    def grep_log_for_errors(self):
        return bash.check_output(dockercmd.exec_cmd(self.name, config.log_error_grep.format(BitcoinNode.log_file)))

    def cat_log_cmd(self):
        return dockercmd.exec_cmd(self.name, 'cat {}'.format(BitcoinNode.log_file))


class PublicBitcoinNode(BitcoinNode, PublicNode):
    def __init__(self, name, ip, latency):
        BitcoinNode.__init__(self, name, ip)
        PublicNode.__init__(self, latency)

    def add_latency(self, zones):
        for cmd in tccmd.create(self.name, zones, self.latency):
            bash.check_output(cmd)


class SelfishPrivateNode(BitcoinNode):
    def __init__(self, name, ip):
        super().__init__(name, ip)


class ProxyNode(Node, PublicNode):
    log_file = '/tmp/selfish_proxy.log'

    def __init__(self, name, ip, private_ip, args, latency):
        Node.__init__(self, name, ip)
        PublicNode.__init__(self, latency)
        self.private_ip = private_ip
        self.args = args

    def run(self, start_hash):
        return bash.check_output(proxycmd.run_proxy(self, start_hash))

    def wait_for_highest_tip_of_node(self, node):
        block_hash = node.execute_rpc('getbestblockhash')
        while block_hash != bash.check_output(proxycmd.get_best_public_block_hash(self.name)):
            utils.sleep(0.2)
            logging.debug('Waiting for  blocks to spread...')

    def cat_log_cmd(self):
        return dockercmd.exec_cmd(self.name, 'cat {}'.format(ProxyNode.log_file))

    def grep_log_for_errors(self):
        return bash.check_output(dockercmd.exec_cmd(self.name, config.log_error_grep.format(ProxyNode.log_file)))

    def add_latency(self, zones):
        for cmd in tccmd.create(self.name, zones, self.latency):
            bash.check_output(cmd)

