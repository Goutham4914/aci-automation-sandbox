#!/usr/bin/env python3
"""
Generate ACI intent YAML files from an input CSV.

Usage:
    python scripts/generate_intent.py inputs/CHG001-new-bds.csv

Supported object types (determined by the 'object_type' column in the CSV):
    bd          - Bridge Domain
    ap          - Application Profile
    epg         - Endpoint Group
    static_path - Static port binding + full interface policy stack (UC1)
    vpc         - vPC port channel between ESXi host and two leaf switches (UC2)

CSV columns:
    object_type, tenant, environment, bd_name/ap_name/epg_name/server_name,
    vrf (bd only), gateway (bd only), scope (bd only),
    ap_name (epg only), bd (epg only),
    vlan_pool_name, vlan_from, vlan_to, domain_name, aep_name,
    link_level_policy, cdp_policy, lldp_policy,
    ap, epg, pod, leaf, interface, encap_vlan, mode (static_path only),
    description
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
INTENT_DIR = REPO_ROOT / "intent"


def generate_bds(rows):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("bridge_domain.yml.j2")

    # Group subnet rows by (tenant, environment, bd_name)
    bds = defaultdict(lambda: {"subnets": []})

    for row in rows:
        key = (row["tenant"], row["environment"], row["bd_name"])
        bd = bds[key]
        bd.update({
            "tenant":      row["tenant"],
            "environment": row["environment"],
            "bd_name":     row["bd_name"],
            "vrf":         row["vrf"],
            "description": row.get("description", ""),
        })
        bd["subnets"].append({
            "gateway": row["gateway"],
            "scope":   row.get("scope", "private"),
        })

    for (tenant, env_name, bd_name), bd_data in bds.items():
        output_dir = INTENT_DIR / env_name / "tenants" / tenant / "bridge_domains"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{bd_name}.yml"
        output_file.write_text(template.render(**bd_data))
        print(f"  Generated: {output_file.relative_to(REPO_ROOT)}")


def generate_aps(rows):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("application_profile.yml.j2")

    seen = set()
    for row in rows:
        key = (row["tenant"], row["environment"], row["ap_name"])
        if key in seen:
            continue
        seen.add(key)

        output_dir = (
            INTENT_DIR / row["environment"] / "tenants" / row["tenant"]
            / "application_profiles" / row["ap_name"]
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "profile.yml"
        output_file.write_text(template.render(
            ap_name=row["ap_name"],
            description=row.get("description", ""),
        ))
        print(f"  Generated: {output_file.relative_to(REPO_ROOT)}")


def generate_epgs(rows):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("epg.yml.j2")

    for row in rows:
        output_dir = (
            INTENT_DIR / row["environment"] / "tenants" / row["tenant"]
            / "application_profiles" / row["ap_name"] / "epgs"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{row['epg_name']}.yml"
        output_file.write_text(template.render(
            epg_name=row["epg_name"],
            bd=row["bd"],
            description=row.get("description", ""),
        ))
        print(f"  Generated: {output_file.relative_to(REPO_ROOT)}")


def generate_static_paths(rows):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("static_path.yml.j2")

    for row in rows:
        output_dir = (
            INTENT_DIR / row["environment"] / "tenants" / row["tenant"] / "static_paths"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        # File named after server + interface e.g. SERVER01-eth1-1.yml
        iface_slug = row["interface"].replace("/", "-")
        output_file = output_dir / f"{row['server_name']}-{iface_slug}.yml"
        output_file.write_text(template.render(**row))
        print(f"  Generated: {output_file.relative_to(REPO_ROOT)}")


def generate_vpcs(rows):
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("vpc_policy_group.yml.j2")

    for row in rows:
        output_dir = (
            INTENT_DIR / row["environment"] / "tenants" / row["tenant"] / "vpc_policy_groups"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{row['server_name']}-vPC.yml"
        output_file.write_text(template.render(**row))
        print(f"  Generated: {output_file.relative_to(REPO_ROOT)}")


GENERATORS = {
    "bd":          generate_bds,
    "ap":          generate_aps,
    "epg":         generate_epgs,
    "static_path": generate_static_paths,
    "vpc":         generate_vpcs,
}


def main(input_csv: str):
    path = Path(input_csv)
    if not path.exists():
        print(f"ERROR: File not found: {input_csv}")
        sys.exit(1)

    # Group rows by object_type
    rows_by_type = defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            obj_type = row.get("object_type", "").strip().lower()
            if obj_type not in GENERATORS:
                print(f"WARNING: Unknown object_type '{obj_type}', skipping row: {row}")
                continue
            rows_by_type[obj_type].append(row)

    for obj_type, rows in rows_by_type.items():
        print(f"\nGenerating {len(rows)} row(s) of type '{obj_type}'...")
        GENERATORS[obj_type](rows)

    print("\nDone. Review generated files, then commit and push.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/generate_intent.py <input_csv>")
        sys.exit(1)
    main(sys.argv[1])
