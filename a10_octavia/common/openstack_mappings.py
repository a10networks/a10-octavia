def hm_type(c, os_hm_type):
    hm_map = {
        'PING': c.slb.hm.ICMP,
        'TCP': c.slb.hm.TCP,
        'HTTP': c.slb.hm.HTTP,
        'HTTPS': c.slb.hm.HTTPS
    }
    return hm_map[os_hm_type]

def service_group_lb_method(c,os_method):
    z = c.slb.service_group
    lb_methods = {
        'ROUND_ROBIN': z.ROUND_ROBIN,
        'LEAST_CONNECTIONS': z.LEAST_CONNECTION,
        'SOURCE_IP': z.SOURCE_IP_HASH,
        'WEIGHTED_ROUND_ROBIN': z.WEIGHTED_ROUND_ROBIN,
        'WEIGHTED_LEAST_CONNECTION': z.WEIGHTED_LEAST_CONNECTION,
        'LEAST_CONNECTION_ON_SERVICE_PORT':
            z.LEAST_CONNECTION_ON_SERVICE_PORT,
        'WEIGHTED_LEAST_CONNECTION_ON_SERVICE_PORT':
            z.WEIGHTED_LEAST_CONNECTION_ON_SERVICE_PORT,
        'FAST_RESPONSE_TIME': z.FAST_RESPONSE_TIME,
        'LEAST_REQUEST': z.LEAST_REQUEST,
        'STRICT_ROUND_ROBIN': z.STRICT_ROUND_ROBIN,
        'STATELESS_SOURCE_IP_HASH': z.STATELESS_SOURCE_IP_HASH,
        'STATELESS_DESTINATION_IP_HASH': z.STATELESS_DESTINATION_IP_HASH,
        'STATELESS_SOURCE_DESTINATION_IP_HASH':
            z.STATELESS_SOURCE_DESTINATION_IP_HASH,
        'STATELESS_PER_PACKET_ROUND_ROBIN':
            z.STATELESS_PER_PACKET_ROUND_ROBIN,
    }
    return lb_methods[os_method]
