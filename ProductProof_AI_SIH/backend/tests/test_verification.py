from app.services.verification import verify

def test_color_mismatch():
    listing={"title":"ExampleTech X1 Black","description":"","brand":"ExampleTech","category":"Smartphone","color":"Black","model":"X1"}
    vision=[{"product_type":"smartphone","brand":"ExampleTech","model":"X1","color":"Blue","visible_text":[],"image_quality":"good","same_product_likelihood":.9,"manipulation_concern":"low"}]
    r=verify(listing,["missing.jpg"],[[]],vision)
    assert r["decision"] in {"REVIEW","REJECT"}
    assert any("color" in x.lower() for x in r["mismatches"])
