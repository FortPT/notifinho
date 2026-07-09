"""
Notifinho

inspect_email.py

Developer tool.

Prints useful information from an .eml file
to help build parsers.
"""

from __future__ import annotations

import sys

from email import policy
from email.parser import BytesParser

from bs4 import BeautifulSoup


def main():

    if len(sys.argv) != 2:

        print("Usage:")

        print("python inspect_email.py file.eml")

        return

    filename = sys.argv[1]

    with open(filename, "rb") as fp:

        message = BytesParser(
            policy=policy.default,
        ).parse(fp)

    print("=" * 70)

    print("SUBJECT")

    print("=" * 70)

    print(message.get("Subject"))

    print()

    html = ""

    if message.is_multipart():

        for part in message.walk():

            if part.get_content_type() == "text/html":

                html = part.get_content()

                break

    elif message.get_content_type() == "text/html":

        html = message.get_content()

    print("=" * 70)

    print("HTML LENGTH")

    print("=" * 70)

    print(len(html))

    print()

    soup = BeautifulSoup(
        html,
        "lxml",
    )

    print("=" * 70)

    print("TABLES")

    print("=" * 70)

    tables = soup.find_all("table")

    print(f"Found {len(tables)} table(s)")

    print()

    for i, table in enumerate(tables, 1):

        print("-" * 70)

        print(f"TABLE {i}")

        print("-" * 70)

        print(table.get_text("\n", strip=True))

        print()


if __name__ == "__main__":

    main()
