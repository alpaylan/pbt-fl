use {
    bst::spec,
    crabcheck::profiling::quickcheck,
    tracing_subscriber::EnvFilter,
};


fn main() {
    let args = std::env::args().collect::<Vec<_>>();
    tracing_subscriber::fmt().with_env_filter(EnvFilter::from_default_env()).with_ansi(true).init();
    if args.len() < 3 {
        eprintln!("Usage: {} <tool> <property>", args[0]);
        eprintln!("Available tools: quickcheck");
        eprintln!(
            "For available properties, check https://github.com/alpaylan/etna-cli/blob/main/docs/workloads/bst.md"
        );
        return;
    }
    let tool = args[1].as_str();
    let property = args[2].as_str();

    let num_tests = 200;

    let result = match (tool, property) {
        ("crabcheck", "insert_valid") => quickcheck(|(t, k, v)| spec::prop_insert_valid(t, k, v)),
        ("quickcheck", "DeleteValid") => quickcheck(|(t, k)| spec::prop_delete_valid(t, k)),
        ("quickcheck", "UnionValid") => quickcheck(|(t1, t2)| spec::prop_union_valid(t1, t2)),
        ("quickcheck", "InsertPost") => {
            quickcheck(|(t, k1, k2, v)| spec::prop_insert_post(t, k1, k2, v))
        },
        ("quickcheck", "DeletePost") => quickcheck(|(t, k1, k2)| spec::prop_delete_post(t, k1, k2)),
        ("quickcheck", "UnionPost") => quickcheck(|(t1, t2, k)| spec::prop_union_post(t1, t2, k)),
        ("quickcheck", "InsertModel") => quickcheck(|(t, k, v)| spec::prop_insert_model(t, k, v)),
        ("quickcheck", "DeleteModel") => quickcheck(|(t, k)| spec::prop_delete_model(t, k)),
        ("quickcheck", "UnionModel") => quickcheck(|(t1, t2)| spec::prop_union_model(t1, t2)),
        ("quickcheck", "InsertInsert") => {
            quickcheck(|(t, k1, k2, v1, v2)| spec::prop_insert_insert(t, k1, k2, v1, v2))
        },
        ("quickcheck", "InsertDelete") => {
            quickcheck(|(t, k1, k2, v)| spec::prop_insert_delete(t, k1, k2, v))
        },
        ("quickcheck", "InsertUnion") => {
            quickcheck(|(t1, t2, k1, k2)| spec::prop_insert_union(t1, t2, k1, k2))
        },
        ("quickcheck", "DeleteInsert") => {
            quickcheck(|(t, k1, k2, v)| spec::prop_delete_insert(t, k1, k2, v))
        },
        ("quickcheck", "DeleteDelete") => {
            quickcheck(|(t, k1, k2)| spec::prop_delete_delete(t, k1, k2))
        },
        ("quickcheck", "DeleteUnion") => {
            quickcheck(|(t1, t2, k)| spec::prop_delete_union(t1, t2, k))
        },
        ("quickcheck", "UnionDeleteInsert") => {
            quickcheck(|(t1, t2, k1, k2)| spec::prop_union_delete_insert(t1, t2, k1, k2))
        },
        ("quickcheck", "UnionUnionIdempotent") => {
            quickcheck(|t| spec::prop_union_union_idempotent(t))
        },
        ("quickcheck", "UnionUnionAssoc") => {
            quickcheck(|(t1, t2, t3)| spec::prop_union_union_assoc(t1, t2, t3))
        },
        _ => {
            panic!("Unknown tool or property: {} {}", tool, property)
        },
    };

    println!("Result: {:?}", result);
}
