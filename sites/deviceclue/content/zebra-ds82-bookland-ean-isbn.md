# Why does a Zebra scanner return 10 digits for a 13-digit book barcode?

A Zebra **DS8208** or **DS8288** can report the same book in two formats. With **Bookland EAN** enabled and **Bookland ISBN-10** selected, a book barcode starting with **978** is sent as its older ten-character ISBN. Choose **Bookland ISBN-13** if your catalog expects the number printed below the main barcode, including the 978 or 979 prefix. [Zebra DS82 Bookland ISBN format](https://docs.zebra.com/us/en/scanners/general/ds8-series/ds82-prg/c-param-desc-symbologies/c-param-desc-upceanjan/r-param-desc-bookland-isbn-format.html)

## Why removing the first three digits gives the wrong result

The older ISBN has its own check digit. For example, the International ISBN Agency printed **978-3-88053-108-6** and **3-88053-108-0** on the same guide. The final **6** in the longer number becomes **0** in the shorter one. An inventory system that simply cuts off the 978 will search for the wrong identifier. [International ISBN Agency guide, title page](https://ebookconverter.creativindie.com/converter/ISBN/doc/ISBN13.pdf#page=1)

## What changes when a book starts with 979?

Zebra's ISBN-10 mode does not recognize a **979** barcode as Bookland. To capture books with either prefix, use **ISBN-13** and send the result to a catalog field that accepts all 13 digits. Changing the scanner setting cannot make a ten-character catalog field hold that value. [Zebra format descriptions](https://docs.zebra.com/us/en/scanners/general/ds8-series/ds82-prg/c-param-desc-symbologies/c-param-desc-upceanjan/r-param-desc-bookland-isbn-format.html)

## Which DS82 settings should you check?

1. **Enable Bookland EAN, parameter 83.** Zebra's factory setting is disabled. Selecting an ISBN format alone leaves this feature off. [Zebra Bookland EAN programming barcodes](https://docs.zebra.com/us/en/scanners/general/ds8-series/ds82-prg/c-param-desc-symbologies/c-param-desc-upceanjan/r-param-desc-bookland-ean.html)
2. **Choose the supplemental setting, parameter 16.** Zebra lists three modes for Bookland. If your stock includes books both with and without the smaller add-on barcode, choose **Autodiscriminate UPC/EAN/JAN with Supplementals**. **Decode UPC/EAN/JAN with Supplementals Only** skips barcodes that lack an add-on. Zebra also provides a **978/979 Supplemental Mode**. [Zebra supplemental decoding options](https://docs.zebra.com/us/en/scanners/general/ds8-series/ds82-prg/c-param-desc-symbologies/c-param-desc-upceanjan/r-param-desc-decode-upceanjan-supplementals-continued-1.html)
3. **Choose Bookland ISBN Format, parameter 576.** Select **ISBN-13** for a field that stores both prefixes. Select **ISBN-10** when an older catalog requires the short form for 978 books. Zebra lists ISBN-10 as the default format. [Zebra DS82 parameter defaults](https://docs.zebra.com/us/en/scanners/general/ds8-series/ds82-prg/c-param-desc-symbologies/r-ds82-symbology-parameter-defaults.html)

## Why are there five more digits beside the ISBN?

After changing the settings, scan a book whose ISBN you can read and compare the result with the catalog's ISBN field. If you see five more digits beside the main barcode, check the supplementary symbol separately. In US book retailing, that smaller symbol can carry price information. [Book Industry Study Group barcoding guidelines](https://www.bisg.org/barcoding-guidelines-for-the-us-book-industry)
