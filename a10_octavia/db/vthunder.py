from a10_octavia.db import models

models.VThunder.create_and_save(amphora_id_id='112', device_name='somename', ip_address='192.168.2.3',
username='username', password='password', axapi_version=30, undercloud=True, loadbalancer_id='lbid',
db_session=None)
