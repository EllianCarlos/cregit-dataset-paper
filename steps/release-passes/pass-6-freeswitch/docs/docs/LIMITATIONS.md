# Known limitations of Token on Me (TOM)

This file gives the known defects of the data of Token on Me (TOM). Read it before you use the
data. COLUMNS.md gives the columns. PRIVACY.md gives the pseudonymization.

## 1. Bare carriage return

A bare carriage return is a CR character that is not followed by an LF character. The dataset
generator read the `.blame` files with universal newlines. Thus it cut a token with a bare CR at
the CR. At each cut, `token_index` has a gap.

A full scan of the first 8,449 project files of the dataset found 555
cut tokens. These tokens are in 77 source files of 8 projects. These project files are not
repaired.

The 150 project files that were added after this scan do not have this defect. Their
generator splits the `.blame` lines on LF only.

## 2. Pseudonymization across batches

By design we do not guarantee that the pseudonymization is stable, since the project ran in
multiple batches and each batch deletes its own salt; a `personid` is stable only inside one
batch.

Thus one person can have different pseudonyms in two project files of different batches. The
project file of `signalwire/freeswitch`, which version 1.1.0 adds, is one more batch with its own salt.

## 3. Committer of two commits

Two commits of the project `signalwire/freeswitch` have two `author` headers. The git library of
the tool (JGit) cannot read the committer of such a commit. For the tokens of these 2 commits, the
tool reads the committer (`committer_name`, `committer_email`, `committer_date`) from the
`committer` header of the commit itself. The values are the values of the header. The tool is
fixed for this case. The other project files are not changed.
