import argparse, json, shutil, time, sqlite3, tempfile, re
from pathlib import Path
from .config import Config
from .generator import generate
from .validation import validate
from .database import create_database, validate_database, export_sql, export_run_snapshot
from .evaluation import evaluate
from .manifest import refresh_manifest, verify_manifest

def main(argv=None):
    parser=argparse.ArgumentParser(prog="plant-sim",description="Generate, validate, run and evaluate a reproducible process simulation")
    sub=parser.add_subparsers(dest="command",required=True)
    for cmd in ("generate","run","all"):
        p=sub.add_parser(cmd); p.add_argument("--profile",choices=["starter","full"],default="starter"); p.add_argument("--scenario",choices=["normal","all"],default="all"); p.add_argument("--seed",type=int,default=20261022); p.add_argument("--telemetry-count",type=int); p.add_argument("--output-dir",default="data/generated")
    v=sub.add_parser("validate");v.add_argument("--input-dir",default="data/generated")
    mf=sub.add_parser("verify-manifest");mf.add_argument("--input-dir",default="data/generated")
    e=sub.add_parser("evaluate");e.add_argument("--run-id");e.add_argument("--input-dir",default="data/generated")
    q=sub.add_parser("export-sql",description="Export INSERT statements from a persisted SQLite run")
    q.add_argument("--db",default="data/generated/simulation.sqlite");q.add_argument("--output",default="sql/seed_data.sql")
    args=parser.parse_args(argv)
    if args.command=="export-sql":
        result=export_sql(args.db,args.output)
        refresh_manifest(Path(args.db).parent,[Path("sql/schema.sql"),result])
        print(json.dumps({"sql_file":str(result),"bytes":result.stat().st_size},indent=2));return 0
    if args.command=="validate":
        result=validate(args.input_dir); print(json.dumps(result,indent=2)); return 0 if result["valid"] else 1
    if args.command=="verify-manifest":
        result=verify_manifest(args.input_dir);print(json.dumps(result,indent=2));return 0 if result["valid"] else 1
    if args.command=="evaluate":
        root=Path(args.input_dir);db=root/"simulation.sqlite"
        try:
            selected=args.run_id
            if db.exists():
                with sqlite3.connect(db) as con:
                    if selected is None:
                        row=con.execute("SELECT simulation_run_id FROM simulation_run ORDER BY rowid DESC LIMIT 1").fetchone()
                        if row is None:raise ValueError("database contains no simulation runs")
                        selected=row[0]
                with tempfile.TemporaryDirectory(prefix="plant-sim-evaluate-") as temp_dir:
                    export_run_snapshot(db,selected,temp_dir)
                    result=evaluate(temp_dir,selected)
                    safe=re.sub(r"[^A-Za-z0-9_.-]","_",selected)
                    shutil.copy2(Path(temp_dir)/"alarms.csv",root/f"alarms-{safe}.csv")
                    shutil.copy2(Path(temp_dir)/"evaluation_summary.json",root/f"evaluation_summary-{safe}.json")
                refresh_manifest(root)
            else:
                result=evaluate(root,selected)
            print(json.dumps(result,indent=2));return 0
        except ValueError as exc:parser.error(str(exc))
    command_started=time.perf_counter()
    run_number=1
    existing_db=Path(args.output_dir)/"simulation.sqlite"
    if existing_db.exists():
        try:
            with sqlite3.connect(existing_db) as con:
                run_ids=[r[0] for r in con.execute("SELECT simulation_run_id FROM simulation_run")]
                run_number=max([int(r.rsplit("-",1)[-1]) for r in run_ids],default=0)+1
        except sqlite3.Error:
            raise SystemExit("Existing database is not a compatible plant-sim database; preserve it and choose a new --output-dir")
    cfg=Config.for_profile(args.profile,args.seed,args.telemetry_count,args.scenario)
    from dataclasses import replace
    cfg=replace(cfg,run_number=run_number)
    m=generate(cfg,args.output_dir); print(json.dumps({"generated":m["row_counts"],"output_dir":str(Path(args.output_dir))},indent=2))
    if args.command in {"run","all"}:
        print(json.dumps(validate(args.output_dir),indent=2)); print(json.dumps(evaluate(args.output_dir),indent=2))
        db_started=time.perf_counter();db=create_database(args.output_dir);db_seconds=time.perf_counter()-db_started
        db_validation=validate_database(db);print(json.dumps(db_validation,indent=2))
        perf_path=Path(args.output_dir)/"performance.json";perf=json.loads(perf_path.read_text());perf["database_persistence_seconds"]=db_seconds
        perf["total_execution_seconds"]=time.perf_counter()-command_started
        perf["generation_preparation_exclusive_seconds"]=max(0.0,perf["generation_total_seconds"]-perf["simulation_seconds"])
        perf["generation_inclusive_seconds"]=perf["generation_total_seconds"]
        perf["validation_and_cli_overhead_seconds"]=max(0.0,perf["total_execution_seconds"]-perf["generation_preparation_exclusive_seconds"]-perf["simulation_seconds"]-perf["detection_seconds"]-db_seconds)
        perf["timing_stages_sum_seconds"]=perf["generation_preparation_exclusive_seconds"]+perf["simulation_seconds"]+perf["detection_seconds"]+db_seconds+perf["validation_and_cli_overhead_seconds"]
        perf["timing_definition"]="Exclusive stages: generation preparation, simulation, detection, database writes. Validation and CLI/output overhead is the residual. generation_inclusive_seconds includes simulation and is informational, not additive. Stages run sequentially."
        perf["telemetry_throughput_per_second"]=cfg.telemetry_count/perf["total_execution_seconds"] if perf["total_execution_seconds"] else None
        perf_path.write_text(json.dumps(perf,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        refresh_manifest(args.output_dir)
    return 0
