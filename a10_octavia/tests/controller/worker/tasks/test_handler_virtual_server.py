from a10_octavia.controller.worker.tasks.handler_virtual_server import CreateVitualServerTask, DeleteVitualServerTask

from a10_octavia.tests.test_base import TestBase

class TestCreateVirtualServerTask(TestBase):
    def setup(self):
        print("Called setup")

    def test_create(self):
        target = CreateVitualServerTask()
        target.execute("", {}, {})
