# Reproducing the Scopus searches

Scopus requires a subscription. The queries are in `search_rerun_worksheet.csv`.

## Running the queries

In Scopus advanced document search (`https://www.scopus.com/search/form.uri?display=advanced`),
for each of the 16 rows:

1. Paste the `scopus_query_with_filters` value into the query box and search.
2. Record the result count in `hits`, and the date in `date_run`.

The filters are part of each query, so the string alone reproduces the search:

    AND LANGUAGE(english)
    AND (DOCTYPE(ar) OR DOCTYPE(cp) OR DOCTYPE(re) OR DOCTYPE(ch))

`ar` = article, `cp` = conference paper, `re` = review, `ch` = book chapter. There is no date
filter: the 2010+ criterion (I2) is applied during screening, so retrieval counts aren't
pre-filtered.

## Deduplicated total

- **Stage 0:** the sum of the 16 individual `hits`, which overlap.
- **Stage 1:** the count of unique documents. `scopus_combined_query.txt` joins all 16 strings
  with `OR`. Combining the search history gives the same result:

      #1 OR #2 OR #3 OR #4 OR #5 OR #6 OR #7 OR #8 OR #9 OR #10 OR #11 OR #12 OR #13 OR #14 OR #15 OR #16

## Interpreting counts

- A count of 0 can mean a quoting error. If it holds, the area is sparse.
- Tens of thousands usually means a lost parenthesis or field prefix.
- String 5c is corrected in the worksheet. The original's missing parentheses matched anything
  mentioning "technical documentation".
