from PIL import Image

from app.services import authenticity


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, count):
        return self._docs[:count]

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.queries = []

    def find(self, query, _projection=None):
        self.queries.append(query)
        docs = []
        for doc in self.docs:
            allowed = True
            for key, condition in query.items():
                if isinstance(condition, dict) and "$ne" in condition:
                    allowed = allowed and doc.get(key) != condition["$ne"]
            if allowed:
                docs.append(doc)
        return FakeCursor(docs)

    def insert_one(self, doc):
        self.docs.append(doc)
        return doc


def _image(tmp_path, name="photo.jpg"):
    path = tmp_path / name
    Image.new("RGB", (64, 64), (140, 40, 40)).save(path, "JPEG")
    return str(path)


def test_same_listing_photos_are_not_duplicates_of_each_other(tmp_path, monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(authenticity, "image_collection", lambda: collection)
    first = _image(tmp_path, "first.jpg")
    second = _image(tmp_path, "second.jpg")

    same_session_1 = authenticity.check_duplicates(first, session_id="session-a")
    same_session_2 = authenticity.check_duplicates(second, session_id="session-a")
    assert same_session_1["duplicate"] is False
    assert same_session_2["duplicate"] is False
    assert all(query == {"session_id": {"$ne": "session-a"}} for query in collection.queries)


def test_reupload_in_another_listing_is_flagged(tmp_path, monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(authenticity, "image_collection", lambda: collection)
    image = _image(tmp_path)

    authenticity.check_duplicates(image, session_id="session-a")
    later = authenticity.check_duplicates(image, session_id="session-b")
    assert later["duplicate"] is True
    assert later["matches"][0]["hamming_distance"] == 0
    assert later["status"] == "ok"


def test_duplicate_check_degrades_without_storage(tmp_path, monkeypatch):
    def unavailable():
        raise RuntimeError("MONGODB_URI is not configured")

    monkeypatch.setattr(authenticity, "image_collection", unavailable)
    result = authenticity.check_duplicates(_image(tmp_path), session_id="s")
    assert result["duplicate"] is False
    assert result["status"] == "not_configured"
