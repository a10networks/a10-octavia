def hm_type(c, os_hm_type):
    hm_map = {
        'PING': c.slb.hm.ICMP,
        'TCP': c.slb.hm.TCP,
        'HTTP': c.slb.hm.HTTP,
        'HTTPS': c.slb.hm.HTTPS
    }
    return hm_map[os_hm_type]
