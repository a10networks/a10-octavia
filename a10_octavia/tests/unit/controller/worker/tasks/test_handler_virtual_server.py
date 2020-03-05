import mock
import uuid

from a10_octavia.controller.worker.tasks.virtual_server_tasks import CreateVitualServerTask, DeleteVitualServerTask
from a10_octavia.tests.test_base import TestBase

USERNAME = "user"
PASSWORD = "pass"

class TestCreateVirtualServerTask(TestBase):
    def setUp(self):
        super(TestCreateVirtualServerTask, self).setUp()
        self.lb_mock = mock.MagicMock()
        self.vthunder_mock = mock.MagicMock(username=USERNAME, password=PASSWORD)
        self.lb_id = str(uuid.uuid4())

    def test_create(self):
        target = CreateVitualServerTask()
        actual = target.execute(self.lb_id, self.lb_mock, self.vthunder_mock)
        self.assertEqual(self.lb_id, actual["loadbalancers"][0]["id"])
