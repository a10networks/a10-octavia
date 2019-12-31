if [$1 == "delete"]:
    openstack loadbalancer member delete mem1
    openstack loadbalancer pool delete pool1
    openstack loadbalancer listener delete l1
else:
    openstack loadbalancer listener create --protocol HTTP --protocol-port 8080 --name l1 lb1
    openstack loadbalancer pool create --protocol HTTP --lb-algorithm ROUND_ROBIN --listener l1 --loadbalancer lb1 pool1
    openstack loadbalancer member create --address 10.0.0.1 --protocol-port 80 --name mem1 pool1
