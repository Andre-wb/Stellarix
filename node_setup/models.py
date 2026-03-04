from pydantic import BaseModel
class SelfSignedRequest(BaseModel):
    hostname: str  = ""
    org_name: str  = "Vortex Node"
    install_ca: bool = True


class LetsEncryptRequest(BaseModel):
    domain: str
    email: str
    staging: bool = False


class ManualCertRequest(BaseModel):
    cert_path: str
    key_path: str

class NodeConfig(BaseModel):
    device_name: str
    port: int = 8000
    host: str = "0.0.0.0"
    max_file_mb: int = 100
    udp_port: int = 4200
    environment: str = "development"