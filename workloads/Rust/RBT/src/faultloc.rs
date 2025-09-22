use {
    crabcheck::profiling::quickcheck,
    rbt::spec,
    tracing_subscriber::EnvFilter,
};

fn main() {
    let args = std::env::args().collect::<Vec<_>>();
    tracing_subscriber::fmt().with_env_filter(EnvFilter::from_default_env()).with_ansi(true).init();
    if args.len() < 3 {
        eprintln!("Usage: {} <tool> <property>", args[0]);
        eprintln!("Available tools: quickcheck");
        eprintln!(
            "For available properties, check https://github.com/alpaylan/etna-cli/blob/main/docs/workloads/rbt.md"
        );
        return;
    }
    let tool = args[1].as_str();
    let property = args[2].as_str();

    let num_tests = 200_000_000;

    let result = match (tool, property) {
        ("crabcheck", "InsertValid") => quickcheck(|(t, k, v)| spec::prop_insert_valid(t, k, v)),
        ("crabcheck", "DeleteValid") => quickcheck(|(t, k)| spec::prop_delete_valid(t, k)),
        ("crabcheck", "InsertPost") => {
            quickcheck(|(t, k1, k2, v)| spec::prop_insert_post(t, k1, k2, v))
        },
        ("crabcheck", "DeletePost") => quickcheck(|(t, k1, k2)| spec::prop_delete_post(t, k1, k2)),
        ("crabcheck", "InsertModel") => quickcheck(|(t, k, v)| spec::prop_insert_model(t, k, v)),
        ("crabcheck", "DeleteModel") => quickcheck(|(t, k)| spec::prop_delete_model(t, k)),
        ("crabcheck", "InsertInsert") => {
            quickcheck(|(t, k1, k2, v1, v2)| spec::prop_insert_insert(t, k1, k2, v1, v2))
        },
        ("crabcheck", "InsertDelete") => {
            quickcheck(|(t, k1, k2, v)| spec::prop_insert_delete(t, k1, k2, v))
        },
        ("crabcheck", "DeleteInsert") => {
            quickcheck(|(t, k1, k2, v)| spec::prop_delete_insert(t, k1, k2, v))
        },
        ("crabcheck", "DeleteDelete") => {
            quickcheck(|(t, k1, k2)| spec::prop_delete_delete(t, k1, k2))
        },
        _ => {
            panic!("Unknown tool or property: {} {}", tool, property)
        },
    };

    println!("Result: {:?}", result);
}
