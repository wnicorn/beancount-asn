#!/usr/bin/env python3
""" Importer for CSV statements from ASN Bank (Volksbank N.V.)"""

__copyright__ = "Copyright (C) 2020-2021 Bram Hooimeijer"
__license__ = "GPLv2"

import csv
import os
import re
import string
import sys
from datetime import timedelta,datetime

import pandas as pd

from beancount.core import data,flags,amount
from beancount.core.number import D
from beancount.ingest import importer


class ASNImporter(importer.ImporterProtocol):
    """An importer for ASN Bank CSV files"""

    def __init__(self, account_root, account_no, payee_map_file):
        self.account_root = account_root
        self.account_no = account_no
        self.csvheader = ['txn_date', 'account', 'contra_account', 'payee',
                'address', 'zipcode', 'city', 'account_comm', 'balance_before',
                'txn_comm', 'amount', 'book_date', 'comm_date', 'intern_code',
                'global_code', 'id', 'reference', 'description', 'copy_id']
        self.payee_map_file = payee_map_file

    def name(self):
        return "ASN Bank CSV Importer"

    def identify(self, file):
        filename = os.path.basename(file.name)
        return re.match('\\d{10}_\\d{8}_\\d{6}\\.csv',
                filename) and (filename[:10]==self.account_no[-10:])

    def file_name(self, file):
        return 'asn_{}'.format(os.path.basename(file.name))

    def file_account(self, _):
        return self.account_root

    def file_date(self, file):
        return datetime.strptime(os.path.basename(file.name).split('_')[1], '%d%m%Y').date()

    def extract(self, file, existing_entries=None):
        try:
            payee_df = pd.read_csv(self.payee_map_file, sep=',', header=0,
                    index_col=0, keep_default_na=False)
        except IOError:
            payee_df = pd.DataFrame(columns=['RAW', 'BC', 'POSTING'])
            print("Writing to new cache {}".format(self.payee_map_file), file=sys.stderr)
        new_payees = {}
        entries = []
        index = 0
        row = {}
        with open(file.name) as file_open:
            for index, row in enumerate(csv.DictReader(file_open, self.csvheader)):
                payee = string.capwords(row['payee'])
                narration = row['description']
                if re.match("^'.*'$", narration):
                    narration = narration[1:-1]
                if re.match('\\s*', payee) and re.match('.*>.*', narration):
                    splt = narration.split('>',1)
                    payee = splt[0]
                    narration = splt[1]
                narration = re.sub("\\s+", " ", narration).strip()
                payee = re.sub("\\s+", " ", payee).strip()
                payee_mpd = map_payee(payee_df, new_payees, payee, row)
                if payee_mpd == "\0":
                    index-=1
                    break

                txn = data.Transaction(
                        meta = data.new_metadata(file.name, index),
                        date = datetime.strptime(row['txn_date'], '%d-%m-%Y').date(),
                        flag = flags.FLAG_OKAY,
                        payee = payee_mpd if payee_mpd else None,
                        narration = narration,
                        tags = set(),
                        links = set(),
                        postings =[],
                        )


                txn.postings.append(
                        data.Posting(self.account_root,
                            amount.Amount(D(row['amount']),row['txn_comm']), None, None, None, None)
                        )
                add_post(txn, payee_df, payee, row)
                entries.append(txn)

        if index:
            entries.append(
                    data.Balance(
                        data.new_metadata(file.name, index),
                        datetime.strptime(row['txn_date'], '%d-%m-%Y').date() + timedelta(days=1),
                        self.account_root,
                        amount.add(
                            entries[index].postings[0].units,
                            amount.Amount(D(row['balance_before']), row['account_comm'])
                            ),
                        None,None
                        )
                    )

        if new_payees:
            new_payees_df = pd.DataFrame(new_payees.items(), columns=['RAW','BC'])
            payee_df.to_csv(self.payee_map_file + ".old")
            payee_df.append(new_payees_df, ignore_index=True).to_csv(self.payee_map_file)
        return entries

def map_payee(payee_df, new_payees, payee:str, row) -> str:
    """
    Refactors the payee using the payees cache. Prompts for
    a new name if payee is not found in the cache.
    """
    if row['contra_account']:
        key = row['contra_account']
    elif payee:
        key = payee
    else:
        key = row['description']
    # Check cache from payee_map_file
    ret = payee_df.loc[payee_df.RAW == key, 'BC']
    if not ret.empty:
        return ret.iloc[0]
    # Check cache with new_payees
    if key in new_payees:
        return new_payees[key]
    # Not found. Prompt for new payee name
    print("New payee in transaction\n"
            "Date: {}\n"
            "Payee: {}\n"
            "Account: {}\n"
            "Amount: {}{}\n"
            "Narration: {}\n"
            "Give a name for {}, = to preserve, q to exit, or s to skip."\
                    .format(
                        row['txn_date'],
                        payee,
                        row['contra_account'],
                        row['txn_comm'],
                        row['amount'],
                        row['description'],
                        key
                        ),
                    file=sys.stderr
                    )
    value = input()
    # Return payee depending on returned value
    if value == "s":
        return payee
    if value == "q":
        return "\0"
    if value == "=":
        value = payee
    if not key:
        return value
    new_payees[key] = value
    print("Adding {} -> {}".format(key, value), file=sys.stderr)
    return value

def add_post(txn, payee_df, payee, row) -> None:
    """
    Adds new postings to txn based on data in payee_df or row
    """
    if row['contra_account']:
        key = row['contra_account']
    elif payee:
        key = payee
    else:
        key = row['description']
    # Check cache from payee_map_file
    ret = payee_df.loc[payee_df.RAW == key, 'POSTING']
    if not ret.empty and ret.iloc[0]:
        txn.postings.append(
                data.Posting(str(ret.iloc[0]),
                    None, None, None, None, None)
                )
