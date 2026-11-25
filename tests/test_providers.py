from rover_status.config import CONTRACTS, DEFAULT_TOPICS, parse_config
from rover_status.providers import resolve


class Capability:
    def __init__(self, provider_id):
        self.provider_id = provider_id


class Channel:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.closed = False

    def close(self):
        self.closed = True


class Atlas:
    def __init__(self, found=None, error=None):
        self.found = found or {}
        self.error = error
        self.queries = []

    def find_capability(self, contract_id, transport, provider_id=""):
        self.queries.append((contract_id, transport, provider_id))
        if self.error:
            raise RuntimeError(self.error)
        return self.found.get(contract_id, [])


class FakeService:
    def __init__(self, endpoints=None, error=None):
        self.endpoints = endpoints or {}
        self.error = error
        self.channels = []

    def connect_capability(self, capability, contract_id, transport):
        if self.error:
            raise RuntimeError(self.error)
        endpoint = self.endpoints.get(contract_id, f"/resolved/{contract_id.rsplit('/', 1)[-1]}")
        channel = Channel(endpoint)
        self.channels.append(channel)
        return channel


def _found_all():
    return {
        contract: [Capability("prov")]
        for contract in CONTRACTS.values()
    }


def test_resolves_every_role_from_atlas():
    atlas = Atlas(_found_all())
    service = FakeService()
    topics, sources, channels = resolve(parse_config({}), service, atlas=atlas)
    assert len(channels) == 6
    for role, contract in CONTRACTS.items():
        assert topics[role] == f"/resolved/{contract.rsplit('/', 1)[-1]}"
        assert sources[role] == "atlas:prov"
    assert len(atlas.queries) == 6
    assert all(query[2] == "" for query in atlas.queries)


def test_provider_id_is_passed():
    atlas = Atlas(_found_all())
    config = parse_config({"provider_ids": {"imu": "wit_imu"}})
    resolve(config, FakeService(), atlas=atlas)
    imu_queries = [q for q in atlas.queries if q[0] == CONTRACTS["imu"]]
    assert imu_queries == [(CONTRACTS["imu"], "ros2", "wit_imu")]


def test_missing_provider_falls_back_to_default_topic():
    atlas = Atlas({CONTRACTS["rtk_status"]: [Capability("gnss")]})
    topics, sources, channels = resolve(
        parse_config({}), FakeService(), atlas=atlas)
    assert topics["rtk_status"] == "/resolved/rtk_status"
    assert topics["imu"] == DEFAULT_TOPICS["imu"]
    assert sources["imu"] == "default (no provider)"
    assert len(channels) == 1


def test_explicit_remap_skips_atlas():
    atlas = Atlas(_found_all())
    config = parse_config({"topic_remap": {"imu": "/custom/imu"}})
    topics, sources, channels = resolve(config, FakeService(), atlas=atlas)
    assert topics["imu"] == "/custom/imu"
    assert sources["imu"] == "config"
    assert not any(q[0] == CONTRACTS["imu"] for q in atlas.queries)
    assert len(channels) == 5


def test_resolution_can_be_disabled():
    atlas = Atlas(_found_all())
    topics, sources, channels = resolve(
        parse_config({"resolve_providers": False}), FakeService(), atlas=atlas)
    assert topics == DEFAULT_TOPICS
    assert set(sources.values()) == {"default"}
    assert channels == []
    assert atlas.queries == []


def test_connect_error_degrades_per_role():
    atlas = Atlas(_found_all())
    service = FakeService(error="boom")
    topics, sources, _ = resolve(parse_config({}), service, atlas=atlas)
    assert topics == DEFAULT_TOPICS
    assert sources["imu"] == "default (connect error: boom)"


def test_empty_and_duplicate_endpoints_are_rejected():
    atlas = Atlas(_found_all())
    service = FakeService(endpoints={CONTRACTS["imu"]: ""})
    topics, sources, channels = resolve(
        parse_config({}), service, atlas=atlas)
    assert topics["imu"] == DEFAULT_TOPICS["imu"]
    assert sources["imu"] == "default (empty endpoint)"
    assert all(channel.closed for channel in service.channels if not channel.endpoint)

    same = "/resolved/shared"
    atlas = Atlas(_found_all())
    service = FakeService(endpoints={contract: same for contract in CONTRACTS.values()})
    topics, sources, channels = resolve(
        parse_config({}), service, atlas=atlas)
    assert len(channels) == 1
    assert sum(1 for source in sources.values()
               if source == "default (duplicate endpoint)") == 5


def test_atlas_error_degrades():
    atlas = Atlas(error="atlas down")
    topics, sources, channels = resolve(
        parse_config({}), FakeService(), atlas=atlas)
    assert channels == []
    assert topics == DEFAULT_TOPICS
    assert sources["fix"] == "default (atlas error: atlas down)"
