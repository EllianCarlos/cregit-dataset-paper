# Known limitations of Token on Me (TOM)

This file gives the known defects of the data of Token on Me (TOM). Read it before you use the
data. COLUMNS.md gives the columns. PRIVACY.md gives the pseudonymization.

## 1. Bare carriage return

A bare carriage return is a CR character that is not followed by an LF character. The dataset
generator read the `.blame` files with universal newlines. Thus it cut a token with a bare CR at
the CR. At each cut, `token_index` has a gap.

A full scan of the 8,449 project files that were in the dataset before this revision found 555
cut tokens. These tokens are in 77 source files of 8 projects. These project files are not
repaired.

The [[tom: added projects]] project files that this revision adds do not have this defect. Their
generator splits the `.blame` lines on LF only.

## 2. Pseudonymization across batches

By design we do not guarantee that the pseudonymization is stable, since the project ran in
multiple batches and each batch deletes its own salt; a `personid` is stable only inside one
batch.

Thus one person can have different pseudonyms in two project files of different batches. The
[[tom: added projects]] projects that this revision adds are one batch with their own salt.
