use {
    crabcheck::quickcheck::quickcheck,
    stlc::{
        spec,
        spec::ExprOpt,
    },
    std::time::Duration,
};

fn main() {
    let args = std::env::args().collect::<Vec<_>>();
    if args.len() < 3 {
        eprintln!("Usage: {} <tool> <property>", args[0]);
        eprintln!("Available tools: quickcheck, crabcheck");
        eprintln!("Available properties: SinglePreserve, MultiPreserve");
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
            "SinglePreserve" => {
                quickcheck(spec::prop_single_preserve as fn(ExprOpt) -> Option<bool>)
            },
            "MultiPreserve" => {
                quickcheck(spec::prop_multi_preserve as fn(ExprOpt) -> Option<bool>)
            },
            _ => panic!("Unknown property: {}", property),
        };
        println!("{:?}", result);
    } else if tool == "quickcheck" {
        let result = match property {
            "SinglePreserve" => {
                qc.quicktest(spec::prop_single_preserve as fn(ExprOpt) -> Option<bool>)
            },
            "MultiPreserve" => {
                qc.quicktest(spec::prop_multi_preserve as fn(ExprOpt) -> Option<bool>)
            },
            _ => panic!("Unknown property: {}", property),
        };
        result.print_status();
    } else {
        panic!("Unknown tool: {}", tool);
    }
}
