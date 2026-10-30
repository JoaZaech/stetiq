# The library's data

Four small files stand in for what a town library already has. Nothing here is generated:
the example stays small enough to read, and `demo.py` loads it as it is.

| File | Rows | Where a real library gets it |
| --- | --- | --- |
| `catalogue.csv` | 7 books | The bibliographic export of the ILS (integrated library system), usually MARC 21 records: `020` ISBN, `245` title, `100` main author, `260`/`264` year, `650` subject headings (`subject`), the local shelf tag (`genre`) and the holding branch from the item record |
| `members.csv` | 4 members | The ILS patron file: card number, name, home branch |
| `loans.csv` | 12 loans | The ILS circulation log: one row per checkout with borrowed, due and (when the book came back) returned dates. Five loans are still open on 2026-10-30, three of them overdue |
| `branches.json` | 2 branches | The library's own directory: code, name, address and head librarian |

Only the ISBN, the card number and the loan id identify anything; they are the
keys the loader joins on. The `genre` column is the loose shelf tag the branches
used for years; `subject` holds the controlled heading cataloguers assign from the
MARC `650` field. Ontology Version 3 deprecates `Genre` in favour of `Subject`
because of exactly that difference.
