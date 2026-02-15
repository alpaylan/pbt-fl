use {
    crabcheck::quickcheck::quickcheck,
    rbt::{
        implementation::Tree,
        spec,
    },
    std::time::Duration,
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
    let mut qc = quickcheck::QuickCheck::new()
        .tests(num_tests)
        .max_tests(num_tests * 2)
        .max_time(Duration::from_secs(60 * 60));

    if tool == "crabcheck" {
        let result = match property {
            "InsertValid" => quickcheck(|(t, k, v)| spec::prop_insert_valid(t, k, v)),
            "DeleteValid" => quickcheck(|(t, k)| spec::prop_delete_valid(t, k)),
            "InsertPost" => quickcheck(|(t, k1, k2, v)| spec::prop_insert_post(t, k1, k2, v)),
            "DeletePost" => quickcheck(|(t, k1, k2)| spec::prop_delete_post(t, k1, k2)),
            "InsertModel" => quickcheck(|(t, k, v)| spec::prop_insert_model(t, k, v)),
            "DeleteModel" => quickcheck(|(t, k)| spec::prop_delete_model(t, k)),
            "InsertInsert" => {
                quickcheck(|(t, k1, k2, v1, v2)| spec::prop_insert_insert(t, k1, k2, v1, v2))
            },
            "InsertDelete" => quickcheck(|(t, k1, k2, v)| spec::prop_insert_delete(t, k1, k2, v)),
            "DeleteInsert" => quickcheck(|(t, k1, k2, v)| spec::prop_delete_insert(t, k1, k2, v)),
            "DeleteDelete" => quickcheck(|(t, k1, k2)| spec::prop_delete_delete(t, k1, k2)),
            _ => panic!("Unknown property: {}", property),
        };
        println!("{:?}", result);
    } else if tool == "quickcheck" {
        let result = match property {
            "InsertValid" => {
                qc.quicktest(spec::prop_insert_valid as fn(Tree, i32, i32) -> Option<bool>)
            },
            "DeleteValid" => {
                qc.quicktest(spec::prop_delete_valid as fn(Tree, i32) -> Option<bool>)
            },
            "InsertPost" => {
                qc.quicktest(spec::prop_insert_post as fn(Tree, i32, i32, i32) -> Option<bool>)
            },
            "DeletePost" => {
                qc.quicktest(spec::prop_delete_post as fn(Tree, i32, i32) -> Option<bool>)
            },
            "InsertModel" => {
                qc.quicktest(spec::prop_insert_model as fn(Tree, i32, i32) -> Option<bool>)
            },
            "DeleteModel" => {
                qc.quicktest(spec::prop_delete_model as fn(Tree, i32) -> Option<bool>)
            },
            "InsertInsert" => {
                qc.quicktest(spec::prop_insert_insert as fn(Tree, i32, i32, i32, i32) -> Option<bool>)
            },
            "InsertDelete" => {
                qc.quicktest(spec::prop_insert_delete as fn(Tree, i32, i32, i32) -> Option<bool>)
            },
            "DeleteInsert" => {
                qc.quicktest(spec::prop_delete_insert as fn(Tree, i32, i32, i32) -> Option<bool>)
            },
            "DeleteDelete" => {
                qc.quicktest(spec::prop_delete_delete as fn(Tree, i32, i32) -> Option<bool>)
            },
            _ => panic!("Unknown property: {}", property),
        };
        result.print_status();
    } else {
        panic!("Unknown tool: {}", tool);
    }
}
