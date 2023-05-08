"""
Integra is a ZeroMQ Zeroconf RPC
This module provides a Zeroconf discovery layer between 0MQ services.
Please note: security issues/access levels are AT YOUR OWN.

by: https://github.com/pmus
"""

import zmq, socket, time, json
from loguru import logger
from functools import wraps
from threading import Thread
from uuid import uuid4
from os import _exit as exit
from zeroconf import ServiceInfo, Zeroconf, ServiceBrowser, ServiceStateChange

""" Globals """
__version__ = "0.0.1"
system_hostname: str = socket.gethostname()
default_short_sleep_sec: float = 0.3
default_long_sleep_sec: int = 1
default_poll_timeout_sec: int = 3
default_wait_timeout: int = 31622400  # 1 yr
default_poll_timeout_sec = 5
default_long_sleep_sec = 10


def myasync(func):
    """Useful async decorator"""

    @wraps(func)
    def async_func(*args, **kwargs):
        func_hl = Thread(target=func, args=args, kwargs=kwargs)
        func_hl.daemon = False
        func_hl.start()
        return func_hl

    return async_func


class ServiceProxy:
    """
    Proxies calls to a ZMQ request.

    :param integra_instance: Instance of Integra.
    :type integra_instance: Integra
    :param service_name: Name of the service.
    :type service_name: str
    """

    def __init__(self, integra_instance, service_name):
        self.integra_instance = integra_instance
        self.service_name = service_name
        self.client_update_service_data()
        self.poller = zmq.Poller()

    def client_update_service_data(self):
        """
        Updates service data and creates ZMQ proxy.
        """
        self.service_data = self.integra_instance.dict_services[self.service_name]
        logger.info(f"Service data: {self.service_data}")
        self.context = zmq.Context()
        self.socket = None
        while not self.socket:
            try:
                self.socket = self.context.socket(zmq.REQ)
            except zmq.error.ZMQError:
                logger.error("Can't renew socket.")  # Windows case
                time.sleep(default_long_sleep_sec)
                pass
        self.remote_ip = (
            self.service_data["ip"]
            if self.service_data["ip"] != self.integra_instance.ip
            else "127.0.0.1"
        )
        self.remote_port = self.service_data["port"]
        logger.info("Creating ZMQ proxy at: %s:%s", self.remote_ip, self.remote_port)
        self.socket.setsockopt(zmq.LINGER, 0)  # Add timeout feature
        self.socket.connect(f"tcp://{self.remote_ip}:{self.remote_port}")

    def __getattr__(self, attr: str, *args, **kwargs) -> object:
        """
        Returns a callable object.

        :param attr: Attribute name.
        :type attr: str
        :return: Callable object.
        :rtype: object
        """

        def do_callable(*args, **kwargs):
            res = self.method_missing(attr, *args, **kwargs)
            return res

        return do_callable

    def method_missing(self, attr, *args, **kwargs):
        """
        Proxies calls to ZMQ request.

        :param attr: Attribute name.
        :type attr: str
        :param args: Arguments.
        :type args: tuple
        :param kwargs: Keyword arguments.
        :type kwargs: dict
        :return: Result of ZMQ request.
        :rtype: object
        """
        request = {
            "service": self.service_name,
            "attr": attr,
            "args": args,
            "kwargs": kwargs,
        }

        self.socket.send_pyobj(request)
        recv = {}

        self.poller.register(self.socket, zmq.POLLIN)
        if self.poller.poll(default_poll_timeout_sec * 1000):
            recv = self.socket.recv_pyobj()
            error = recv.get("error", None)
            if error:
                raise error

        else:
            logger.error(f"Service {self.service_name} lost.")
            while not self.service_name in self.integra_instance.dict_services:
                time.sleep(default_long_sleep_sec)
            self.client_update_service_data()  # This is service recovery
        return recv.get("result", None)


class Integra:
    """
    Integra is a Zeroconf discovery layer between 0MQ services.
    """

    def __init__(self, zmq_port=None, local_only=False, debug=False):
        """
        Initialize Integra object.

        :param zmq_port: Port number for ZMQ. If None, a random port will be used.
        :type zmq_port: int
        :param local_only: If True, ZMQ will only serve on localhost. Default is False.
        :type local_only: bool
        :param debug: If True, debug logging will be enabled. Default is False.
        :type debug: bool
        """
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0)
            s.connect(("10.254.254.254", 1))
            self.ip: str = s.getsockname()[0]
        self.run: bool = True
        self.zeroconf: Zeroconf = Zeroconf()
        self.dict_objects: dict = dict()
        self.dict_services: dict = dict()
        self.zmq_addr: str = "127.0.0.1" if local_only else "*"
        self.zmq_port: int = 0
        self.uuid: str = f"{uuid4()}"
        self.desc: dict = dict({"uuid": self.uuid, "services": [], "ip": self.ip})
        self.context: zmq.Context = zmq.Context()
        self.socket: zmq.Context.socket = self.context.socket(zmq.REP)
        self.browser: ServiceBrowser = ServiceBrowser(
            self.zeroconf,
            ["_http._tcp.local.", "ipc._http._tcp.local."],
            handlers=[self.on_service_state_change],
        )
        self.server_loop()

    @myasync
    def server_loop(self):
        """
        Server side of ZMQ.
        """
        addr: str = f"tcp://{self.zmq_addr}:*"  # Take any free port
        self.socket.bind(addr)
        real_endpoint = self.socket.getsockopt(zmq.LAST_ENDPOINT).decode()
        logger.success(f"Integra: started. ZMQ serves at {real_endpoint}")
        self.zmq_port = int(real_endpoint.split(":")[2])
        reply: dict = dict()
        while self.run:
            try:
                request: object = self.socket.recv_pyobj()
            except zmq.error.ContextTerminated:
                break
            service, attr, args, kwargs = (
                request["service"],
                request["attr"],
                request["args"],
                request["kwargs"],
            )

            try:
                service_obj: object = self.dict_objects[service]
            except Exception as e:
                logger.error(f"Service object {service} missing: {e}")
                reply["error"] = RuntimeError(f"Service object {service} missing.")

            service_attr = getattr(service_obj, attr, None)
            if not service_attr:
                logger.error(f"No attribute {attr} in {service}.")
                reply["error"] = AttributeError(f"No attribute {attr} in {service}.")

            if callable(service_attr):
                res = service_attr(*args, **kwargs)
            else:
                res = service_attr

            reply["result"] = res
            self.socket.send_pyobj(reply)

    def on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ):
        """
        Callback function for Zeroconf service state changes.

        :param zeroconf: Zeroconf object.
        :type zeroconf: Zeroconf
        :param service_type: Type of service.
        :type service_type: str
        :param name: Name of service.
        :type name: str
        :param state_change: State change of service.
        :type state_change: ServiceStateChange
        """
        service_info = zeroconf.get_service_info(service_type, name)
        info: dict = self.service_info_to_dict(service_info) if service_info else dict()

        if info.get("uuid", None) == self.uuid:
            return None

        logger.info(f"Service {name} -> {service_type} state change: {state_change}")

        if state_change is ServiceStateChange.Removed:
            for service_name in list(self.dict_services):
                item: dict = self.dict_services[service_name]
                if item["name"] == name:
                    del self.dict_services[service_name]
                    logger.warning(f"deleting service: {name}")
            return

        if info.get("services", None):
            for service_name in info["services"]:
                if service_name not in list(self.dict_services):
                    self.dict_services[service_name] = info

    def service_info_to_dict(self, service_info: ServiceInfo) -> dict:
        """
        Convert ServiceInfo object to dictionary.

        :param service_info: ServiceInfo object.
        :type service_info: ServiceInfo
        :return: Dictionary representation of ServiceInfo object.
        :rtype: dict
        """
        res: dict = {}
        res["name"] = service_info.name
        res["port"] = int(service_info.port)
        res["server"] = service_info.server
        properties: dict = service_info.properties
        properties = dict(
            {
                key.decode("utf-8"): value.decode("utf-8")
                for key, value in properties.items()
            }
        )
        properties["services"] = json.loads(properties["services"].replace("'", '"'))
        res.update(properties)
        return res

    def add_service(self, service_name: str, some_object: object) -> None:
        """
        Add a service to Integra.

        :param service_name: Name of service.
        :type service_name: str
        :param some_object: Object to be served.
        :type some_object: object
        """
        self.dict_objects[service_name] = some_object
        self.desc["services"].append(service_name)
        logger.info(f"Registering service '{service_name}'...")
        str_ipc = f"ipc-{self.uuid}._http._tcp.local."
        info: ServiceInfo = ServiceInfo(
            "_http._tcp.local.",
            str_ipc,
            addresses=[socket.inet_aton(self.ip)],
            port=self.zmq_port,
            properties=self.desc,
            server=f"{system_hostname}.local.",
        )

        self.zeroconf.register_service(
            info
        ) if not self.dict_objects else self.zeroconf.update_service(info)

        logger.success(f"Serving '{service_name}'...")

    def get_service_proxy(self, service_name: str) -> ServiceProxy:
        """
        Get a proxy for a specified service.

        :param service_name: Name of service.
        :type service_name: str
        :return: ServiceProxy object.
        :rtype: ServiceProxy
        """
        if not service_name in self.dict_services:
            return None

        service_item = self.dict_services.get(service_name, None)
        logger.info(f"Service '{service_name}' found as {service_item}")
        return ServiceProxy(self, service_name)

    def get_service_wait(
        self, service_name: str, timeout: int = default_wait_timeout
    ) -> ServiceProxy:
        time_waited: int = 0
        res: ServiceProxy = None
        logger.info(f"Waiting for service {service_name}, timeout={timeout}...")
        while not res and time_waited < timeout:
            res: ServiceProxy = self.get_service_proxy(service_name)
            time.sleep(1) if not res else ...
            time_waited += 1
        if not res:
            raise RuntimeError(f"Service {service_name} not found.")
        return res

    def __setitem__(self, service_name: str, some_object: object) -> None:
        """
        Same as add_service, but maybe easier way to type.
        """
        self.add_service(service_name, some_object)

    def __getitem__(self, service_name: str) -> ServiceProxy:
        """
        Same as get_service_wait, but maybe easier way to type.
        """
        return self.get_service_wait(service_name)


ipc: Integra = Integra()

if __name__ == "__main__":
    logger.warning("This is a module, do not run this directly.")
    exit(0)
