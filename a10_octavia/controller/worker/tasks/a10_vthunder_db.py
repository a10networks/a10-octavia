from a10_octavia.db import repositories as repo
from a10_octavia.db import api as db_apis
from oslo_utils import uuidutils


class VThunderDB():
    def __init__(self, **kwargs):
        self.vthunder_repo = repo.VThunderRepository()

    def create_vthunder(self, device_name, username, password, ip_address, undercloud=None, axapi_version=30, loadbalancer_id=None):
        print("Inside create vThunder")
        if axapi_version == 2.1:
            axapi_version = 21
        else:
            axapi_version = 30
        amphora_id = uuidutils.generate_uuid()

        if undercloud == 'True' or undercloud == 'true':
            undercloud = True
        else:
            undercloud = False
        
        db_session = db_apis.get_session()
        vthunder = self.vthunder_repo.create(db_session, amphora_id=amphora_id,
                                             device_name=device_name, username=username,
                                             password=password, ip_address=ip_address,
                                             undercloud=undercloud, axapi_version=axapi_version,
                                             loadbalancer_id=loadbalancer_id)
        db_apis.close_session(db_session)

        print("vThunder entry created successfully.")

    def update_vthunder():
        print("Update vThunder")

    def delete_vthunder():
        print("Delete vThunder")
