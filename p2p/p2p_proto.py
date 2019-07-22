from typing import (
    cast,
    Any,
    Dict,
    Tuple,
)

from eth_utils.toolz import assoc

import rlp
from rlp import sedes

from p2p.abc import TransportAPI
from p2p.disconnect import DisconnectReason as _DisconnectReason
from p2p.exceptions import MalformedMessage
from p2p.typing import PayloadType

from p2p.protocol import (
    Command,
    Protocol,
)


class Hello(Command):
    _cmd_id = 0
    decode_strict = False
    structure = (
        ('version', sedes.big_endian_int),
        ('client_version_string', sedes.text),
        ('capabilities', sedes.CountableList(sedes.List([sedes.text, sedes.big_endian_int]))),
        ('listen_port', sedes.big_endian_int),
        ('remote_pubkey', sedes.binary)
    )

    def decompress_payload(self, raw_payload: bytes) -> bytes:
        # The `Hello` command doesn't support snappy compression
        return raw_payload

    def compress_payload(self, raw_payload: bytes) -> bytes:
        # The `Hello` command doesn't support snappy compression
        return raw_payload


class Disconnect(Command):
    _cmd_id = 1
    structure = (('reason', sedes.big_endian_int),)

    def get_reason_name(self, reason_id: int) -> str:
        try:
            return _DisconnectReason(reason_id).name
        except ValueError:
            return "unknown reason"

    def decode(self, data: bytes) -> PayloadType:
        try:
            raw_decoded = cast(Dict[str, int], super().decode(data))
        except rlp.exceptions.ListDeserializationError:
            self.logger.warning("Malformed Disconnect message: %s", data)
            raise MalformedMessage(f"Malformed Disconnect message: {data}")
        return assoc(raw_decoded, 'reason_name', self.get_reason_name(raw_decoded['reason']))


class Ping(Command):
    _cmd_id = 2
    structure = ()


class Pong(Command):
    _cmd_id = 3
    structure = ()


class P2PProtocol(Protocol):
    name = 'p2p'
    version = 5
    _commands = (Hello, Ping, Pong, Disconnect)
    cmd_length = 16

    def __init__(self,
                 transport: TransportAPI,
                 snappy_support: bool,
                 capabilities: Tuple[Tuple[str, int], ...],
                 listen_port: int) -> None:
        # For the base protocol the cmd_id_offset is always 0.
        # For the base protocol snappy compression should be disabled
        super().__init__(transport, cmd_id_offset=0, snappy_support=snappy_support)
        self.capabilities = capabilities
        self.listen_port = listen_port

    def send_handshake(self) -> None:
        # TODO: move import out once this is in the trinity codebase
        from trinity._utils.version import construct_trinity_client_identifier
        data = dict(version=self.version,
                    client_version_string=construct_trinity_client_identifier(),
                    capabilities=self.capabilities,
                    listen_port=self.listen_port,
                    remote_pubkey=self.transport.public_key.to_bytes())
        header, body = Hello(self.cmd_id_offset, self.snappy_support).encode(data)
        self.transport.send(header, body)

    def send_disconnect(self, reason: _DisconnectReason) -> None:
        msg: Dict[str, Any] = {"reason": reason}
        header, body = Disconnect(
            self.cmd_id_offset,
            self.snappy_support
        ).encode(msg)
        self.transport.send(header, body)

    def send_pong(self) -> None:
        header, body = Pong(self.cmd_id_offset, self.snappy_support).encode({})
        self.transport.send(header, body)
