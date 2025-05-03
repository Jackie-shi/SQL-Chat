global QA_PATH
global TABLE_PATH
QA_PATH = './qa.csv'
TABLE_JSON_PATH = './auto_dump_table_info.json'

DATA2URL = {
    'submarine_': 'https://ki3.org.cn/#/fiberOpticCommunication?sub=cableOverview',
    'as_': 'https://ki3.org.cn/#/asInformation?sub=asBasicInfo',
    # 'bgp_hijack_': 'https://test.kdp.ki3.org.cn/#/bgpRoutingInformation?sub=prefixHijack',
    'bgp_': 'https://ki3.org.cn/#/rpkiDeployment?sub=rpkiAnalysis&children=rovData',
    'badbgp_': 'https://ki3.org.cn/#/rpkiDeployment?sub=rpkiAnalysis&children=rovData',
    'active_ip_': 'https://ki3.org.cn/#/ipAssignment?sub=ipv4',
    'dns_dependency_': 'https://ki3.org.cn/#/dnsDependence?sub=dnsDependencyExploration',
    'dns_resolver_': 'https://ki3.org.cn/#/dnsInfo',
    'dnsroot_': 'https://ki3.org.cn/#/dnsServerInfo',
    'ip_allocation_': 'https://ki3.org.cn/#/ipAssignment',
    'ipv4_': 'https://ki3.org.cn/#/ipAssignment?sub=ipv4',
    'ipv6_': 'https://ki3.org.cn/#/ipAssignment?sub=ipv6',
    'ixp_': 'https://ki3.org.cn/#/ixpInformation?sub=ixpMap',
    'ntp_': 'https://ki3.org.cn/#/ntpSystem?sub=ntpDeploy',
    'prefix_': 'https://ki3.org.cn/#/asInformation?sub=asBasicInfo',
    'base_region': 'https://ki3.org.cn/#/asInformation?sub=asBasicInfo',
    'revoke_': 'https://ki3.org.cn/#/rpkiDeployment',
    'rir_': 'https://ki3.org.cn/#/ipAssignment',
    'roas_': 'https://ki3.org.cn/#/rpkiDeployment',
    'rpki_': 'https://ki3.org.cn/#/rpkiDeployment',
    'roas': 'https://ki3.org.cn/#/rpkiDeployment',
    'root_': 'https://ki3.org.cn/#/dnsServerInfo?sub=rootDNS',
    'sav_': 'https://ki3.org.cn/#/sav',
    'satellite_': 'https://ki3.org.cn/#/satelliteCommunication',
    'tld': 'https://ki3.org.cn/#/dnsServerInfo?sub=topDNS',
    'tld_': 'https://ki3.org.cn/#/dnsServerInfo?sub=topDNS',
    'total_': 'https://ki3.org.cn/#/rpkiDeployment',
    'update': 'https://ki3.org.cn/#/rpkiDeployment',
    'tls_': 'https://ki3.org.cn/#/httpsProtocol'
} 

import logging  # Setting up the loggings to monitor gensim
global logger
logger = logging.getLogger('my_logger_public')
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('run_public.log')
formatter = logging.Formatter('%(levelname)s - %(asctime)s: %(message)s')
file_handler.setFormatter (formatter)
logger.addHandler(file_handler)