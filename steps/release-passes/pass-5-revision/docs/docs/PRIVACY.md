# Personal data and pseudonymization in Token on Me (TOM)

The commits hold the names and the e-mail addresses of persons. TOM does not publish them. A
pseudonymizer replaced them before the release. Pseudonymized data can still be personal data
under data protection law (for example the Brazilian LGPD, Lei 13.709/2018). Use the data only for
research. Do not try to identify a person.

## 1. The pseudonymized columns

| Columns | Value in TOM |
|---|---|
| `author_name`, `committer_name` | `Author ` and 14 hexadecimal characters |
| `personid` | `author ` and 14 hexadecimal characters |
| `author_email`, `committer_email` | `author_` and 14 hexadecimal characters, then the at sign and the domain. With no valid domain, only `author_` and the 14 hexadecimal characters |
| `footer_*` (13 trailer arrays) | Each element `Name <address>`: the name and the address as above |
| `footer_personids` | Each element as `personid` |

The pseudonym is a nested keyed sha256 of the value in lower case. The key came from a private
salt. The salt was deleted after the write, so nobody can compute a pseudonym of this scheme again.
By design we do not guarantee that the pseudonymization is stable, since the project ran in
multiple batches and each batch deletes its own salt; a `personid` is stable only inside one
batch. LIMITATIONS.md gives the details.

`person_domain` is not pseudonymized. It is a DNS domain, and DNS domains are public on the web.
The release keeps it in lower case, with no leading or trailing spaces, because the organization
link uses it. When the input holds an at sign, only the first valid domain after an at sign stays,
else the value is empty. The domain part of the addresses also stays.

## 2. Other columns with personal data

- The project columns (columns 1 to 17 of COLUMNS.md). Some projects are in the account of a
  person.
- `source_text` and `token_value` (the code) and `commit_summary` (the first line of the commit
  message). They can hold names and addresses.
- The commit hashes and the project names. They let a reader find the original commit and its
  author on the host.

## 3. Residual risks

- Many domains have one person only. A domain of one person can identify that person.
- Some domains are host names of work computers. A host name can hold the user name of a person.
