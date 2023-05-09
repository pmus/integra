import zmq, socket, time, json
from loguru import logger
from uuid import uuid4
from zeroconf import ServiceInfo, Zeroconf, ServiceBrowser, ServiceStateChange
from functools import wraps
from threading import Thread

__version__ = "0.0.2"
system_hostname: str = socket.gethostname()
default_short_sleep_sec: float = 0.1
default_poll_timeout_sec: int = 3
default_wait_timeout: int = 10


def myasync(func) -> None:

    @wraps(func)
    def async_func(*args, **kwargs):
        func_hl = Thread(target=func, args=args, kwargs=kwargs)
        func_hl.daemon = False
        func_hl.start()
        return func_hl

    return async_func


class ServiceProxy(object):

    def __init__(self, integra_instance, service_name) -> None:
        self.integra_instance: Integra = integra_instance
        self.service_name: str = service_name
        self.client_update_service_data()

    def client_update_service_data(self):
        self.service_data: dict = self.integra_instance.dict_services[self.service_name]
        logger.info(f"Service data: {self.service_data}")
        self.context: zmq.Context = zmq.Context()
        self.socket: zmq.Context.socket = None
        while not self.socket:
            try:
                self.socket: zmq.Context.socket = self.context.socket(zmq.REQ)
            except zmq.error.ZMQError:
                logger.error("Can't renew socket.")  # Special Windows case
                time.sleep(default_poll_timeout_sec)
        self.remote_ip = (self.service_data["ip"]
                          if self.service_data["ip"] != self.integra_instance.ip else "127.0.0.1")
        self.remote_port = self.service_data["port"]
        logger.info(f"Creating ZMQ proxy at: {self.remote_ip}:{self.remote_port}")
        self.socket.setsockopt(zmq.LINGER, 0)  # Add timeout feature
        self.socket.connect(f"tcp://{self.remote_ip}:{self.remote_port}")

    def __getattr__(self, attr) -> object:

        def callable(*args, **kwargs):
            res: object = self.method_missing(attr, *args, **kwargs)
            return res

        return callable

    def method_missing(self, attr, *args, **kwargs) -> object:
        request: dict = dict({
            "service": self.service_name,
            "attr": attr,
            "args": args,
            "kwargs": kwargs,
        })

        self.socket.send_pyobj(request)
        recv: dict = dict()
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        if poller.poll(default_poll_timeout_sec * 1000):
            recv, error = self.socket.recv_pyobj(), recv.get("error", None)
            if error:
                raise error

        else:
            logger.warning(f"Service {self.service_name} lost.")
            self.integra_instance.forget_service(self.service_name)
            logger.info(f"Waiting for service {self.service_name}.")
            while not self.service_name in self.integra_instance.dict_services:
                time.sleep(default_poll_timeout_sec)
            self.client_update_service_data()  # This is service recovery
        return recv["result"] if recv else None


class Integra(object):

    def __init__(self, zmq_port: int = 0, local_only=False, debug=False) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0)
            s.connect(("10.254.254.254", 1))  # on error,
            self.ip: str = s.getsockname()[0]  # we don't mute it.
        self.run: bool = True
        self.zeroconf: Zeroconf = Zeroconf()
        self.dict_objects: dict = dict()  # What I offer
        self.dict_services: dict = dict()  # What do neighbours offer
        self.zmq_addr: str = "127.0.0.1" if local_only else "*"
        self.zmq_port = zmq_port
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
    def server_loop(self) -> None:
        addr: str = f"tcp://{self.zmq_addr}:*"  # Server-side ZMQ, take a free port
        self.socket.bind(addr)
        real_endpoint = self.socket.getsockopt(zmq.LAST_ENDPOINT).decode()
        logger.success(f"Integra: started. ZMQ serves at {real_endpoint}")
        self.zmq_port = int(real_endpoint.split(":")[2])
        reply: dict = dict()
        while self.run:
            try:
                request: object = self.socket.recv_pyobj()
            except zmq.error.ContextTerminated:
                break  # It *will* be terminated on exit.
            service, attr, args, kwargs = (
                request["service"],
                request["attr"],
                request["args"],
                request["kwargs"],
            )

            try:
                service_obj: object = self.dict_objects[service]
            except Exception as e:
                reply["error"] = RuntimeError(f"Error {e}: Service object {service} missing.")

            service_attr = getattr(service_obj, attr, None)
            if not service_attr:
                reply["error"] = AttributeError(f"No attribute {attr} in {service}.")
            res = service_attr(*args, **kwargs) if callable(service_attr) else service_attr
            reply["result"] = res
            self.socket.send_pyobj(reply)

    def on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        """state_change in: ServiceStateChange.Added, .Updated or .Removed"""
        service_info = zeroconf.get_service_info(service_type, name)
        info: dict = self.service_info_to_dict(service_info) if service_info else dict()
        logger.info(f"Service {name} -> {service_type} state change: {state_change}")

        if info.get("uuid", None) == self.uuid:
            return  # This is myself
        elif state_change is ServiceStateChange.Removed:
            self.forget_service(name)
        elif state_change is ServiceStateChange.Added:
            for service_name in info["services"]:
                self.dict_services[service_name] = info

    def forget_service(self, name) -> None:
        logger.info(f"Deleting {name} from {self.dict_services}")
        del self.dict_services[name]

    def service_info_to_dict(self, service_info: ServiceInfo) -> dict:
        res: dict = {}
        res["name"] = service_info.name
        res["port"] = int(service_info.port)
        res["server"] = service_info.server
        properties: dict = service_info.properties
        properties = dict({
            key.decode("utf-8"): value.decode("utf-8")
            for key, value in properties.items()
        })  # Properties transmitted in binary, we decode...
        properties["services"] = json.loads(properties["services"].replace("'", '"'))
        # This is not my fault, but zeroconf passes them this way ---------^^^
        res.update(properties)
        return res

    def add_service(self, service_name: str, some_object: object) -> None:
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

        self.zeroconf.register_service(info) if not self.dict_objects else self.zeroconf.update_service(info)
        logger.success(f"Serving '{service_name}' as {self.uuid}...")

    def get_service_proxy(self, service_name: str) -> ServiceProxy:
        if not service_name in self.dict_services:
            return None

        service_item = self.dict_services.get(service_name, None)
        logger.info(f"Service '{service_name}' found as {service_item}")
        return ServiceProxy(self, service_name)

    def get_service_wait(self, service_name: str, timeout: int = default_wait_timeout) -> ServiceProxy:
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
        self.add_service(service_name, some_object)

    def __getitem__(self, service_name: str) -> ServiceProxy:
        return self.get_service_wait(service_name)


ipc: Integra = Integra()  # You can just: from integra import ipc