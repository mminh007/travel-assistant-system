import json
import re

raw_text = """
1 Grand Hotel Furama 141 Đường Trần Phú, Nha Trang 0258.3246316
2 Grand Hotel Furama Luxury 48 Đường Trần Phú, Nha Trang 0258.3629903
3 Premier Residence Melia Hội An 230 Đường Hai Bà Trưng, Hội An 0235.3948749
4 Grand Hotel Meridian Luxury 80 Đường Hùng Vương, Huế 0234.3452944
5 Premier Residence Vinpearl 177 Đường Nguyễn Thiện Thuật, Nha Trang 0258.3946335
6 Luxury Resort Oasis Hội An 283 Đường Trần Hưng Đạo, Hội An 0235.3748564
7 Grand Hotel Silkotel 41 Đường Trần Hưng Đạo, Đà Nẵng 0236.3498591
8 Luxury Resort Belvedere Luxury 108 Đường Hùng Vương, Huế 0234.3816751
9 Eco Lodge Melia Đà Nẵng 237 Đường Bạch Đằng, Đà Nẵng 0236.3771088
10 Boutique Hotel Monarque Luxury 17 Đường Hùng Vương, Nha Trang 0258.3380746
11 Eco Lodge Haven 256 Đường Trường Sa, Đà Nẵng 0236.3581141
12 Ocean View Hotel Vinpearl Đà Nẵng 288 Đường Trường Sa, Đà Nẵng 0236.3883300
13 Resort & Spa Meridian 253 Đường Nguyễn Văn Linh, Đà Nẵng 0236.3149405
14 Eco Lodge Greenery Luxury 33 Đường Nguyễn Duy Hiệu, Hội An 0235.3724834
15 Ocean View Hotel Meridian Nha Trang 59 Đường Lê Thánh Tôn, Nha Trang 0258.3379786
16 Luxury Resort Pearl Luxury 2 Đường Lê Duẩn, Đà Nẵng 0236.3898975
17 Premier Residence Novotel 260 Đường Phan Chu Trinh, Huế 0234.3260263
18 Resort & Spa Blue Ocean Huế 10 Đường Bến Nghé, Huế 0234.3972064
19 Resort & Spa Meridian 249 Đường Trần Phú, Nha Trang 0258.3658582
20 Premier Residence Haian Luxury 271 Đường Trần Hưng Đạo, Đà Nẵng 0236.3322086
21 Riverside Hotel Royal Riverside Huế 265 Đường Bến Nghé, Huế 0234.3359947
22 Grand Hotel Heritage Luxury 284 Đường Phạm Văn Đồng, Nha Trang 0258.3330914
23 Boutique Hotel Mulberry 17 Đường Võ Nguyên Giáp, Đà Nẵng 0236.3639131
24 Premier Residence Imperial Đà Nẵng 68 Đường Nguyễn Văn Linh, Đà Nẵng 0236.3595631
25 Eco Lodge Silver Sand 50 Đường Võ Nguyên Giáp, Đà Nẵng 0236.3544154
26 Boutique Hotel Silkotel Luxury 207 Đường Trần Phú, Nha Trang 0258.3360735
27 Luxury Resort Sapphire Đà Nẵng 94 Đường Lê Duẩn, Đà Nẵng 0236.3361941
28 Khách sạn Little Beach Luxury 277 Đường Lê Thánh Tôn, Nha Trang 0258.3890170
29 Eco Lodge La Residencia 110 Đường Lý Thường Kiệt, Hội An 0235.3272634
30 Ocean View Hotel Paragon Hội An 217 Đường Cửa Đại, Hội An 0235.3853305
31 Ocean View Hotel La Residencia 297 Đường Võ Nguyên Giáp, Đà Nẵng 0236.3884309
32 Apartment & Hotel La Residencia Luxury 272 Đường Nguyễn Duy Hiệu, Hội An 0235.3632496
33 Eco Lodge Royal Riverside Nha Trang 121 Đường Lê Thánh Tôn, Nha Trang 0258.3697347
34 Premier Residence Crystal Luxury 299 Đường Hùng Vương, Hội An 0235.3431737
35 Luxury Resort Sapphire 68 Đường Bến Nghé, Huế 0234.3431535
36 Grand Hotel Pearl Nha Trang 276 Đường Trần Phú, Nha Trang 0258.3378082
37 Apartment & Hotel Diamond 146 Đường Trần Hưng Đạo, Đà Nẵng 0236.3974244
38 Apartment & Hotel Vinpearl Luxury 54 Đường Phan Chu Trinh, Huế 0234.3221035
39 Grand Hotel Central Huế 310 Đường Hùng Vương, Huế 0234.3459536
40 Eco Lodge Melia Luxury 48 Đường Lê Lợi, Huế 0234.3146228
41 Ocean View Hotel Central 227 Đường Nguyễn Huệ, Huế 0234.3548462
42 Boutique Hotel Heritage Đà Nẵng 19 Đường Nguyễn Văn Linh, Đà Nẵng 0236.3679364
43 Khách sạn Silver Sand 187 Đường Nguyễn Thiện Thuật, Nha Trang 0258.3320281
44 Grand Hotel InterContinental Luxury 80 Đường Nguyễn Duy Hiệu, Hội An 0235.3938742
45 Eco Lodge Paragon Đà Nẵng 171 Đường Trường Sa, Đà Nẵng 0236.3870763
46 Riverside Hotel Furama Luxury 20 Đường Tuệ Tĩnh, Nha Trang 0258.3309267
47 Grand Hotel Monarque 13 Đường Bạch Đằng, Đà Nẵng 0236.3444207
48 Boutique Hotel Green Heaven Hội An 275 Đường Hùng Vương, Hội An 0235.3220944
49 Boutique Hotel Vista 223 Đường Phạm Văn Đồng, Nha Trang 0258.3924629
50 Eco Lodge Sunrise Luxury 23 Đường Trần Hưng Đạo, Đà Nẵng 0236.3645175
51 Resort & Spa Vista Huế 161 Đường Trần Hưng Đạo, Huế 0234.3414910
52 Grand Hotel Sala Luxury 66 Đường Trần Hưng Đạo, Huế 0234.3797229
53 Grand Hotel Haian 147 Đường Nguyễn Thiện Thuật, Nha Trang 0258.3923927
54 Apartment & Hotel Paragon Đà Nẵng 243 Đường Nguyễn Văn Linh, Đà Nẵng 0236.3188914
55 Grand Hotel Novotel 159 Đường Trường Sa, Đà Nẵng 0236.3254511
56 Riverside Hotel Sala Luxury 38 Đường Nguyễn Duy Hiệu, Hội An 0235.3760356
57 Khách sạn Meridian Đà Nẵng 336 Đường Bạch Đằng, Đà Nẵng 0236.3907451
58 Riverside Hotel La Residencia Luxury 266 Đường Trường Sa, Đà Nẵng 0236.3684482
59 Ocean View Hotel Majestic 342 Đường Lê Duẩn, Đà Nẵng 0236.3724377
60 Riverside Hotel Vinpearl Hội An 244 Đường Hai Bà Trưng, Hội An 0235.3888295
61 Resort & Spa Central 226 Đường Trần Hưng Đạo, Đà Nẵng 0236.3399607
62 Apartment & Hotel Anantara Luxury 42 Đường Trần Hưng Đạo, Huế 0234.3342495
63 Ocean View Hotel Sapphire Hội An 170 Đường Lý Thường Kiệt, Hội An 0235.3535970
64 Premier Residence Greenery Luxury 11 Đường Nguyễn Duy Hiệu, Hội An 0235.3600149
65 Ocean View Hotel Serene 276 Đường Lý Thường Kiệt, Hội An 0235.3331251
66 Boutique Hotel Paragon Hội An 200 Đường Trần Hưng Đạo, Hội An 0235.3812131
67 Premier Residence Paragon 304 Đường Tuệ Tĩnh, Nha Trang 0258.3128418
68 Luxury Resort Greenery Luxury 26 Đường Hai Bà Trưng, Hội An 0235.3443254
69 Eco Lodge Vinpearl Huế 143 Đường Bến Nghé, Huế 0234.3975467
70 Resort & Spa Zenith Luxury 115 Đường Nguyễn Thiện Thuật, Nha Trang 0258.3783414
71 Apartment & Hotel Hyatt Regency 319 Đường Võ Nguyên Giáp, Đà Nẵng 0236.3232352
72 Premier Residence Serene Huế 86 Đường Hùng Vương, Huế 0234.3884256
73 Eco Lodge Monarque 295 Đường Nguyễn Thiện Thuật, Nha Trang 0258.3849747
74 Premier Residence Royal Riverside Luxury 155 Đường Lê Thánh Tôn, Nha Trang 0258.3934904
75 Boutique Hotel Sunrise Huế 260 Đường Lê Lợi, Huế 0234.3990844
76 Apartment & Hotel Haian Luxury 236 Đường Phan Chu Trinh, Huế 0234.3284692
77 Premier Residence Melia 224 Đường Lý Thường Kiệt, Hội An 0235.3437960
78 Premier Residence Tranquil Hội An 238 Đường Hai Bà Trưng, Hội An 0235.3800646
79 Grand Hotel Silver Sand 250 Đường Nguyễn Huệ, Huế 0234.3936587
80 Ocean View Hotel Novotel Luxury 6 Đường Trần Hưng Đạo, Huế 0234.3189771
81 Riverside Hotel Diamond Đà Nẵng 244 Đường Trường Sa, Đà Nẵng 0236.3931450
82 Luxury Resort Paragon Luxury 125 Đường Lê Duẩn, Đà Nẵng 0236.3709805
83 Luxury Resort Muong Thanh 233 Đường Hùng Vương, Huế 0234.3363615
84 Apartment & Hotel Novotel Huế 275 Đường Lê Lợi, Huế 0234.3326895
85 Luxury Resort Furama 100 Đường Lê Lợi, Huế 0234.3478411
86 Khách sạn Majestic Luxury 24 Đường Trần Hưng Đạo, Đà Nẵng 0236.3406327
87 Riverside Hotel Golden Lotus Huế 246 Đường Bến Nghé, Huế 0234.3293319
88 Riverside Hotel Mulberry Luxury 206 Đường Trần Phú, Nha Trang 0258.3705050
89 Resort & Spa Majestic 128 Đường Lê Lợi, Huế 0234.3901577
90 Eco Lodge Muong Thanh Hội An 302 Đường Cửa Đại, Hội An 0235.3696251
91 Resort & Spa InterContinental 339 Đường Trần Hưng Đạo, Đà Nẵng 0236.3351516
92 Riverside Hotel Belvedere Luxury 210 Đường Võ Nguyên Giáp, Đà Nẵng 0236.3722656
93 Riverside Hotel Mulberry Huế 145 Đường Phan Chu Trinh, Huế 0234.3820775
94 Grand Hotel Haven Luxury 279 Đường Trần Hưng Đạo, Hội An 0235.3256226
95 Premier Residence Centara 305 Đường Trần Hưng Đạo, Đà Nẵng 0236.3560485
96 Ocean View Hotel Ruby Hội An 257 Đường Cửa Đại, Hội An 0235.3559023
97 Khách sạn Little Beach 129 Đường Trần Hưng Đạo, Huế 0234.3340044
98 Riverside Hotel Melia Luxury 266 Đường Lê Duẩn, Đà Nẵng 0236.3290305
99 Boutique Hotel Paragon Huế 171 Đường Bến Nghé, Huế 0234.3209680
100 Eco Lodge Meridian Luxury 340 Đường Cửa Đại, Hội An 0235.3676818
"""

lines = [l.strip() for l in raw_text.strip().split('\n')]
hotels = []
for line in lines:
    parts = line.split()
    stt = parts[0]
    phone = parts[-1]
    rest = " ".join(parts[1:-1])
    
    city = ""
    if ", Nha Trang" in rest:
        city = "Nha Trang"
        name_addr = rest.split(", Nha Trang")[0]
    elif ", Đà Nẵng" in rest:
        city = "Đà Nẵng"
        name_addr = rest.split(", Đà Nẵng")[0]
    elif ", Hội An" in rest:
        city = "Hội An"
        name_addr = rest.split(", Hội An")[0]
    elif ", Huế" in rest:
        city = "Huế"
        name_addr = rest.split(", Huế")[0]
    
    match = re.search(r'\s(\d+\sĐường.*)', name_addr)
    if match:
        address = match.group(1).strip()
        name = name_addr[:match.start()].strip()
    else:
        name = name_addr
        address = ""
        
    hotels.append({
        "Name": name,
        "Address": address,
        "City": city,
        "PhoneNumber": phone
    })

with open(r"d:\proj\Booking\website\Data\hotels_seed.json", "w", encoding="utf-8") as f:
    json.dump(hotels, f, indent=2, ensure_ascii=False)

print("Created hotels_seed.json")
