"""Public image notices visually verified in SPEC-232; fresh hashes are mandatory."""

from typing import TypedDict


class ImageNotice(TypedDict):
    deadline: str
    expression: str
    fingerprint: str
    images: list[tuple[str, str]]


IMAGE_NOTICES: dict[str, ImageNotice] = {
    "c03ac1e9-ba89-4954-b894-3218d0df5191.htm": {
        "deadline": "2023-06-11T17:00:00+08:00",
        "expression": "报名时间：2023年5月31日—2023年6月11日17:00（正文第4页）",
        "fingerprint": "61a04a136dc8efddbb4ab58294ad8fe02dff405af33446131823aa7ca578617f",
        "images": [
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2023-05-31/090c213c-9f17-48e7-8733-bd227345a2dd.jpg",
                "4ee93f3e441803c885d78b96702505d7bd87d5eed385a88fd80361889abe5a26",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2023-05-31/10736bdb-8e53-419b-9b05-221548cacdaf.jpg",
                "998dfab68e663ce79a214961cb908aae6c124d336c9636c031c222eed4ee32b6",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2023-05-31/273b0b42-c557-48df-9540-d471053a90e6.jpg",
                "a47ac56b69fa601869aa1fd73decc749a1208dbe26d13c1704a32fc722627b41",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2023-05-31/7afa5a8d-3ec6-4ec4-ac16-7775f9037a28.jpg",
                "9a128e6172c9dcdf922a4fb3d5dec1ed9f66b8295886cc2b48b90c6368baa22e",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2023-05-31/3c05c60d-dbd7-4b26-ad56-6ace9430af20.jpg",
                "f74df260025d6e3599e7361c0e669564b44023d9ee0b1a5628370e7ceb88ad68",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2023-05-31/dc087f03-4686-4034-bda9-5a2d6def74fb.jpg",
                "16f37f91107e88c653bc995ac5df7ca5ae8fb365d3d38a05ef8537a4f62a2179",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2023-05-31/489b23ee-fb17-4ea6-92e0-04ecb7a87a06.jpg",
                "b47896e1587c6b27514953287d41bed6e1163cdcdd74ffd30bec04e78687be9a",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2023-05-31/a802d165-7666-4c65-b7e9-2e87150a7b02.jpg",
                "7ece92e98f88217106c9c287eb08cdc67ca2a68e87eb631c73b8b77344a6fbc3",
            ),
        ],
    },
    "c538c0e0-31f1-4927-8055-df6a70b31af3.htm": {
        "deadline": "2022-07-31T00:00:00+08:00",
        "expression": "报名截止时间2022年7月30日24:00（正文第5页）",
        "fingerprint": "3d3a464dfab4cc00aa1ccefbf2603287995cb1a1359dff3368f0d59ea3425e71",
        "images": [
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2022-07-20/d42e3aef-1598-439f-bb1f-35060ff41b06.jpg",
                "9dba42eb6a658954b8440ef35b31c20af31da4e9f364e78fcb2688436bffa058",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2022-07-20/7998a9c9-9c30-4170-beb7-09598eb8b01f.jpg",
                "e51b4d85f2df7d88f097dc9045d7fcd469a7d78b5acc404ae0d943e472422b72",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2022-07-20/96db09b2-d69d-4965-846a-7862bb5a0ad4.jpg",
                "81ada6a931e7d84687e290d1600469021b70a7fa8877085023a28784f370774d",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2022-07-20/3e4b2331-0fad-4260-aba9-f61b8d24ccf9.jpg",
                "3473d670c38fb1bf7d070ce94e3977eea5a8d7bd6d74af9d95b44bb040728ffa",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2022-07-20/ccb9f551-6c82-4971-b0b2-0a2bc71752e1.jpg",
                "ad538ad8f422b7450981af7817a9f2f978f179882dab550547fb797296b53c76",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2022-07-20/4bb3a434-aa90-4cb9-971d-aaa28a3bf290.jpg",
                "f7ae21cd57524be64141ba6e271fe329957c65ca2c56302303fc0179bc21f5e8",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2022-07-20/c5a74bab-0390-43ce-8776-964eab8b1c9d.jpg",
                "fc173233680a4a28d68de49a306d84c56eb5b527ae37c955d23b3f3972f97694",
            ),
            (
                "https://www.cnyig.com/Uploads/NewsPhoto/2022-07-20/bff8d662-5b62-4441-8350-d9255168f1a5.jpg",
                "dca092ded5df0ea0597d653e62947b0c3cda7d7da2c4920771474ecb4ef4305b",
            ),
        ],
    },
    "a96dfd5a-4db8-4b90-bafe-ec3afc915071.htm": {
        "deadline": "2019-11-19T17:00:00+08:00",
        "expression": "报名时间2019年11月7日至2019年至11月19日17:00（正文第5页，源文含至字重复）",
        "fingerprint": "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b",
        "images": [
            (
                "https://www.cnyig.com/temp/image/original/1573198347165.png",
                "3bd579e7b4e4029fcbe6c789f4a2b1ca59c4bd3aaff1c90040ccc2db94a199b5",
            ),
            (
                "https://www.cnyig.com/temp/image/original/1573198363147.png",
                "1a1fccf344fd45cedc6aad3465fa7946488a396fa2be062b38ade7ec0f0e7604",
            ),
            (
                "https://www.cnyig.com/temp/image/original/1573198377466.png",
                "011cb0790c01797166f04318cfbd7c09c44ab4d2237c82666c3cc42477ee6e8f",
            ),
            (
                "https://www.cnyig.com/temp/image/original/1573198398555.png",
                "05404c5cbc93d3ab64a0f677466af293ac97148e516255f0cae8ca01c1575d44",
            ),
            (
                "https://www.cnyig.com/temp/image/original/1575275386081.jpg",
                "94c74e2a27525cd16215aa1fbd09d06f154d0c07674ffbeab8100dfd3a66e476",
            ),
            (
                "https://www.cnyig.com/temp/image/original/1573198431048.png",
                "f26e50527d6c5d716e30fa1d6c3810158444812a57935d2bf1b35dff0d8a2b94",
            ),
            (
                "https://www.cnyig.com/temp/image/original/1573198445780.png",
                "8eb536e4d80d7cb89345339eb8c48baeabdd165d9f3a2a989a3cec60884c13ee",
            ),
            (
                "https://www.cnyig.com/temp/image/original/1573198461533.png",
                "18072c925324ec6d3f90010e81d1733afc4ee05b8338ccd1bd1db36ac6f9526a",
            ),
        ],
    },
}

# Verified QR codes and position tables in otherwise textual notices.
TEXT_IMAGES: dict[str, list[tuple[str, str]]] = {
    "60fb9991-f6dd-45c6-9fa6-41b0f32e26a8.html": [
        (
            "https://www.cnyig.com/Uploads/NewsPhoto/2026-03-30/a5a19c0d-bee6-48cd-bf25-5dd8476375b4.png",
            "bb968c84d3338232b5e5b9ebd8d7b3cdfe31faabddac6a68e449ed24dd3d39e1",
        )
    ],
    "964090b0-adfb-4355-a62c-97f4f8da2dde.html": [
        (
            "https://www.cnyig.com/Uploads/NewsPhoto/2025-07-25/2e7877a9-c914-4cf3-80ed-94389208f3a3.png",
            "a6ebde89b022940994cf533aa6ad40747eb54485a9eaeb4cc0fc2cae7f1301f8",
        )
    ],
    "a80d6f11-153e-4548-a18a-ff9f6e559d53.html": [
        (
            "https://www.cnyig.com/Uploads/NewsPhoto/2024-08-05/391bb23f-bda8-4bf3-a062-c2edc263d663.jpg",
            "b55fb9c068ef397999cabd9479acf7b5c9bc0dea3df6a585b393068c92587c34",
        ),
        (
            "https://www.cnyig.com/Uploads/NewsPhoto/2024-08-05/d5707149-2e78-489c-a8f1-6d1044dce885.jpg",
            "bf20305ab4238a918a93276a47142b7aa2cefe5d8e09d8bac968f9c21f3f0d93",
        ),
    ],
    "7d69f97b-67c3-4e70-90dc-8e35169a40b3.html": [
        (
            "https://www.cnyig.com/Uploads/NewsPhoto/2024-06-08/62be3dbd-2d30-43b9-8eb0-414afcb47295.png",
            "f4753ea14e2ebf4a82d2c5568910be9f1c99e43970d97d310b32a30d1f41bc17",
        )
    ],
    "edce8d76-b4ec-44be-a02f-54d07e510131.htm": [
        (
            "https://www.cnyig.com/temp/image/original/1519717037419.jpg",
            "6860c5ad8cecbd3d743aabed62f241938c13a8d90d59a93ddfe647522a061c47",
        )
    ],
}
